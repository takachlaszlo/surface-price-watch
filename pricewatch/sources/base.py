"""Base class every source adapter derives from."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..delivery import Delivery
from ..http import HttpClient
from ..matcher import Matcher
from ..models import Offer, normalize_merchant


@dataclass
class SourceContext:
    http: HttpClient
    matcher: Matcher


class Source(ABC):
    """One configured source (`sources:` entry in config.yaml).

    `fetch()` returns offers for the monitored product only. Adapters raise
    `BlockedError` / `FetchError` from the HTTP client untouched; the runner
    turns them into the per-source status shown in the report.
    """

    def __init__(self, source_id: str, options: dict[str, Any], ctx: SourceContext):
        self.id = source_id
        self.options = options
        self.http = ctx.http
        self.matcher = ctx.matcher
        self.log = logging.getLogger(f"pricewatch.source.{source_id}")

    @abstractmethod
    def fetch(self) -> list[Offer]:
        ...

    @staticmethod
    def link_for(page: dict, merchant: str, default: str) -> str:
        """Direct product link for a merchant when the page config knows one (`merchant_links`)."""
        key = normalize_merchant(merchant)
        for name, url in (page.get("merchant_links") or {}).items():
            if normalize_merchant(name) == key:
                return url
        return default

    def offer(self, *, country: str, merchant: str, title: str, price: float, currency: str,
              url: str, shipping: float | None = None, availability: str | None = None,
              variant: str | None = None, delivery: Delivery | None = None) -> Offer:
        return Offer(
            delivery=delivery or Delivery(),
            source=self.id,
            country=country.upper(),
            merchant=merchant.strip(),
            title=title.strip(),
            price=float(price),
            currency=currency.upper(),
            url=url,
            shipping=shipping,
            availability=availability,
            variant=variant if variant is not None else self.matcher.variant_label(title),
        )
