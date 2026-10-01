"""Core data types shared by sources, storage and the report."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# code -> (Hungarian name, flag, local currency)
COUNTRIES: dict[str, tuple[str, str, str]] = {
    "CH": ("Svájc", "🇨🇭", "CHF"),
    "HU": ("Magyarország", "🇭🇺", "HUF"),
    "AT": ("Ausztria", "🇦🇹", "EUR"),
    "DE": ("Németország", "🇩🇪", "EUR"),
}

_LEGAL_FORMS = re.compile(r"\b(gmbh|ag|kft\.?|zrt\.?|e\.k\.|kg|shop|online\s*shop|direkt)\b", re.IGNORECASE)
_HOST_NOISE = re.compile(r"^(https?://)?(www\.)?|\.(ch|de|at|hu|com|net|eu|shop)(/.*)?$", re.IGNORECASE)


def normalize_merchant(name: str) -> str:
    """'www.Galaxus.ch', 'Galaxus' and 'galaxus.ch' must collapse to one key;
    so must 'BRACK.CH AG' / 'Brack' and 'Jacob Elektronik direkt' / 'Jacob Elektronik'."""
    cleaned = _LEGAL_FORMS.sub(" ", name).strip(" -")
    cleaned = _HOST_NOISE.sub("", cleaned)
    return re.sub(r"[^a-z0-9]+", "", cleaned.lower()) or name.strip().lower()


@dataclass
class Offer:
    source: str  # id of the configured source that produced the offer
    country: str  # market the merchant sells in: CH / HU / AT / DE
    merchant: str
    title: str
    price: float
    currency: str
    url: str
    shipping: float | None = None
    availability: str | None = None
    variant: str = ""
    price_eur: float | None = None  # filled in by the runner

    @property
    def merchant_key(self) -> str:
        return normalize_merchant(self.merchant)

    @property
    def dedup_key(self) -> tuple[str, str, str]:
        return (self.country, self.merchant_key, self.variant.lower())

    def total(self) -> float:
        return self.price + (self.shipping or 0.0)


@dataclass
class SourceResult:
    source_id: str
    status: str  # ok | empty | blocked | robots | error
    offers: int = 0
    message: str = ""
    duration: float = 0.0


@dataclass
class RunResult:
    run_id: int
    run_date: str
    offers: list[Offer] = field(default_factory=list)
    sources: list[SourceResult] = field(default_factory=list)
    fx: dict[str, float] = field(default_factory=dict)  # units of currency per 1 EUR
    fx_note: str = ""
