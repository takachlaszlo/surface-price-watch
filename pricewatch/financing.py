"""Instalment offers of Hungarian shops – above all: can it be bought at 0% THM (APR)?

Like delivery, this is deliberately not a yes/no flag: "yes" only when the shop
states a 0% THM plan for this very product, "possible" when the shop runs 0% THM
plans but the product page does not say whether this product qualifies, "no" when
the shop's own rules exclude it (e.g. price outside the plan's range).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .parse import clean, parse_price, soup

_RANK = {"": 0, "no": 1, "possible": 2, "yes": 3}

# "151 580 FT x 4 HÓ THM: 0% | Önerő: 151 580 FT"
_PLAN = re.compile(
    r"(?P<amount>\d[\d\s .]*)\s*F[Tt]\s*[x×]\s*(?P<months>\d+)\s*H[ÓO]\b[^%]{0,40}?THM:?\s*(?P<thm>\d+(?:[.,]\d+)?)\s*%"
    r"(?:\s*\|?\s*(?:Önrész|Önerő):?\s*(?P<down>\d[\d\s .]*)\s*F[Tt])?",
    re.IGNORECASE,
)


def _huf(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " Ft"


@dataclass
class Financing:
    thm0: str = ""    # "" unknown | "no" | "possible" | "yes"
    terms: str = ""   # the 0% plan, or why it is (not) available
    other: str = ""   # further plans with their THM

    def merge(self, other: "Financing") -> "Financing":
        """A product-specific statement beats a general one."""
        if _RANK[other.thm0] > _RANK[self.thm0]:
            return Financing(other.thm0, other.terms, self.other or other.other)
        return Financing(self.thm0, self.terms or (other.terms if other.thm0 == self.thm0 else ""),
                         self.other or other.other)

    def known(self) -> bool:
        return bool(self.thm0 or self.other)

    def line_hu(self) -> str:
        head = {
            "yes": "0% THM: igen",
            "possible": "0% THM: lehetséges",
            "no": "0% THM: nincs",
            "": "0% THM: nincs adat",
        }[self.thm0]
        if self.terms:
            head += f" – {self.terms}"
        return head + (f" · további: {self.other}" if self.other else "")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Financing":
        data = data or {}
        thm0 = data.get("thm0", "")
        if isinstance(thm0, bool):
            thm0 = "yes" if thm0 else "no"
        return cls(thm0=str(thm0 or ""), terms=str(data.get("terms") or ""), other=str(data.get("other") or ""))


def from_page(html: str) -> Financing:
    """Read the instalment boxes of a product page ("… FT x 4 HÓ THM: 0% | Önerő: … FT")."""
    doc = soup(html)
    plans: list[tuple[str, float, int, float, float | None]] = []
    boxes = doc.select('[class*="loan-box"]')
    texts = [(clean(b.select_one(".title").get_text(" ")) if b.select_one(".title") else "", clean(b.get_text(" ")))
             for b in boxes]
    if not texts:  # other shops: look for the same wording anywhere in the page text
        texts = [("", clean(doc.get_text(" ")))]
    for label, text in texts:
        for match in _PLAN.finditer(text):
            amount = parse_price(match.group("amount"))
            if amount is None:
                continue
            down = parse_price(match.group("down")) if match.group("down") else None
            plans.append((label, amount, int(match.group("months")),
                          float(match.group("thm").replace(",", ".")), down))
    if not plans:
        return Financing()
    zero = [p for p in plans if p[3] == 0]
    paid = sorted((p for p in plans if p[3] > 0), key=lambda p: p[3])
    other = "; ".join(
        f"{label or 'áruhitel'} {months} hó, THM {str(thm).rstrip('0').rstrip('.').replace('.', ',')}%"
        for label, _amount, months, thm, _down in paid[:2]
    )
    if zero:
        label, amount, months, _thm, down = max(zero, key=lambda p: p[2])  # the longest 0% plan
        terms = f"{months} × {_huf(amount)}" + (f" + {_huf(down)} önerő" if down else "") + (f" ({label})" if label else "")
        return Financing("yes", terms, other)
    return Financing("no", "a terméklapon csak kamatos konstrukció szerepel", other)


def for_price(rule: dict, price: float) -> Financing:
    """A shop-wide rule from config.yaml (`merchant_financing`), applied to one offer's price."""
    info = Financing.from_dict(rule)
    low, high = rule.get("min_price"), rule.get("max_price")
    parts = rule.get("instalments")
    if parts and info.thm0 == "yes":  # equal parts of this very price
        info.terms = f"{int(parts)} × {_huf(price / int(parts))} – {info.terms}"
    if info.thm0 in ("yes", "possible") and ((low and price < low) or (high and price > high)):
        limits = f"{_huf(low or 0)} – {_huf(high)}" if high else f"{_huf(low)} felett"
        return Financing("no", f"{info.terms}: csak {limits} közötti kosárra, ez az ár kívül esik".replace(
            "felett közötti", "feletti"), info.other)
    return info
