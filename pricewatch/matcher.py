"""Decides whether an offer title is the monitored product and labels its variant."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_VARIANT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("Platin", re.compile(r"plat(in|inum|ina)|ezüst|silber", re.I)),
    ("Fekete", re.compile(r"schwarz|black|fekete|graphit", re.I)),
    ("OLED", re.compile(r"\boled\b", re.I)),
    ("LCD", re.compile(r"\blcd\b", re.I)),
    ("5G", re.compile(r"\b5g\b|\blte\b", re.I)),
]


@dataclass
class Matcher:
    must_match: list[str] = field(default_factory=list)
    must_not_match: list[str] = field(default_factory=list)
    mpns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._must = _compile(self.must_match)
        self._must_not = _compile(self.must_not_match)
        self._mpns = [re.compile(re.escape(m), re.IGNORECASE) for m in self.mpns if m]

    def rejects(self, title: str) -> bool:
        return any(rx.search(title) for rx in self._must_not)

    def matches(self, title: str, mpn: str | None = None) -> bool:
        """True when the title (or a known part number) identifies the product.

        A known MPN is accepted even if the shop's title is terse, but the
        exclusion list always wins (e.g. "refurbished", "B-Ware").
        """
        haystack = f"{title} {mpn or ''}"
        if self.rejects(haystack):
            return False
        if any(rx.search(haystack) for rx in self._mpns):
            return True
        return bool(self._must) and all(rx.search(title) for rx in self._must)

    def find_mpn(self, text: str) -> str | None:
        for rx, mpn in zip(self._mpns, [m for m in self.mpns if m]):
            if rx.search(text):
                return mpn
        return None

    @staticmethod
    def variant_label(title: str, extra: str = "") -> str:
        text = f"{title} {extra}"
        labels = [name for name, rx in _VARIANT_RULES if rx.search(text)]
        return ", ".join(labels)
