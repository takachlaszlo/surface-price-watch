"""Parsing helpers used by the source adapters."""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from bs4 import BeautifulSoup

_CURRENCY_HINTS = (
    (re.compile(r"CHF|Fr\.|SFr", re.I), "CHF"),
    (re.compile(r"€|EUR", re.I), "EUR"),
    (re.compile(r"\bFt\b|HUF", re.I), "HUF"),
)


def soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # lxml missing on exotic platforms
        return BeautifulSoup(html, "html.parser")


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_currency(text: str) -> str | None:
    for rx, code in _CURRENCY_HINTS:
        if rx.search(text):
            return code
    return None


def parse_price(value: Any) -> float | None:
    """Parse European price notations.

    Handles "1'099.–", "CHF 1’099.00", "1.099,00 €", "€ 1.099,-",
    "459 990 Ft", "459.990 Ft", "1099.9" and plain numbers.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value)
    # drop "–", "-" placeholders for zero cents ("1'099.–", "1.099,-")
    text = re.sub(r"[.,]\s*[–—-]+", "", text)
    text = re.sub(r"[\s   '’`]", "", text)
    match = re.search(r"\d[\d.,]*", text)
    if not match:
        return None
    num = match.group(0).rstrip(".,")
    if "." in num and "," in num:
        decimal = "." if num.rfind(".") > num.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        num = num.replace(thousands, "").replace(decimal, ".")
    else:
        sep = "." if "." in num else "," if "," in num else None
        if sep:
            head, _, tail = num.rpartition(sep)
            if num.count(sep) > 1 or len(tail) == 3:
                num = num.replace(sep, "")  # thousands separator
            else:
                num = head + "." + tail
    try:
        result = float(num)
    except ValueError:
        return None
    return result if result > 0 else None


def iter_jsonld(html: str) -> Iterator[dict]:
    """Yield every JSON-LD object in the page, flattening @graph and lists."""
    for tag in soup(html).find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            continue
        yield from _flatten(data)


def _flatten(node: Any) -> Iterator[dict]:
    if isinstance(node, list):
        for item in node:
            yield from _flatten(item)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _flatten(node["@graph"])


def _is_type(node: dict, wanted: str) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(isinstance(k, str) and k.lower() == wanted.lower() for k in kinds)


def jsonld_products(html: str) -> list[dict]:
    return [n for n in iter_jsonld(html) if _is_type(n, "Product") or _is_type(n, "ProductGroup")]


def jsonld_offers(product: dict) -> list[dict]:
    """Normalise the offers of a JSON-LD Product to dicts with price/currency/etc."""
    raw = product.get("offers")
    nodes = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    out: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if _is_type(node, "AggregateOffer"):
            inner = node.get("offers")
            inner = inner if isinstance(inner, list) else [inner] if isinstance(inner, dict) else []
            parsed = [o for o in (_offer(i, node) for i in inner if isinstance(i, dict)) if o]
            if parsed:
                out.extend(parsed)
                continue
            low = parse_price(node.get("lowPrice") or node.get("price"))
            if low:
                out.append({
                    "price": low,
                    "currency": node.get("priceCurrency"),
                    "availability": _availability(node.get("availability")),
                    "url": node.get("url"),
                    "seller": None,
                })
        else:
            parsed_one = _offer(node, {})
            if parsed_one:
                out.append(parsed_one)
    return out


def _offer(node: dict, parent: dict) -> dict | None:
    price = node.get("price")
    if price is None and isinstance(node.get("priceSpecification"), (dict, list)):
        spec = node["priceSpecification"]
        spec = spec[0] if isinstance(spec, list) and spec else spec
        if isinstance(spec, dict):
            price = spec.get("price")
            node = {**node, "priceCurrency": node.get("priceCurrency") or spec.get("priceCurrency")}
    value = parse_price(price)
    if not value:
        return None
    seller = node.get("seller") or node.get("offeredBy")
    if isinstance(seller, dict):
        seller = seller.get("name")
    return {
        "price": value,
        "currency": node.get("priceCurrency") or parent.get("priceCurrency"),
        "availability": _availability(node.get("availability")),
        "url": node.get("url"),
        "seller": seller if isinstance(seller, str) else None,
        "condition": _availability(node.get("itemCondition")),
    }


def _availability(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.rsplit("/", 1)[-1] or None
