"""Prices a person looked up by hand – for shops that turn automated visitors away.

galaxus.ch / digitec.ch answer every automated client (and even an automated
browser tab) with a "Bist du ein Roboter?" check, and that check is not worked
around. What a human reads off the page can still take part in the ranking:
put it into a small YAML file in the data folder. Entries expire, so a
forgotten price cannot pose as today's cheapest offer.

/data/kezi_arak.yaml:
    - merchant: Galaxus
      country: CH
      price: 1499
      currency: CHF            # optional, default = the country's currency
      url: https://www.galaxus.ch/de/s1/product/54161673
      variant: Platin          # optional
      date: 2026-10-01         # the day the price was read

config.yaml:
    - id: kezi_arak
      adapter: manual
      options: {file: /data/kezi_arak.yaml, max_age_days: 7}
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from ..http import FetchError
from ..models import COUNTRIES, Offer
from ..parse import parse_price
from . import register
from .base import Source


@register("manual")
class ManualSource(Source):
    def fetch(self) -> list[Offer]:
        path = Path(self.options.get("file", "/data/kezi_arak.yaml"))
        if not path.exists():
            return []
        try:
            entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except (OSError, yaml.YAMLError) as exc:
            raise FetchError(f"hibás kézi árfájl ({path.name}): {exc}") from exc
        if not isinstance(entries, list):
            raise FetchError(f"hibás kézi árfájl ({path.name}): listát várok")
        return self.parse(entries, date.today())

    def parse(self, entries: list, today: date) -> list[Offer]:
        max_age = int(self.options.get("max_age_days", 7))
        offers: list[Offer] = []
        for entry in entries:
            try:
                seen = entry["date"]
                seen = seen if isinstance(seen, date) else datetime.strptime(str(seen), "%Y-%m-%d").date()
                country = str(entry["country"]).upper()
                price = parse_price(entry["price"])
                merchant, url = str(entry["merchant"]), str(entry["url"])
                if price is None or country not in COUNTRIES:
                    raise ValueError("ár vagy ország")
            except (KeyError, TypeError, ValueError) as exc:
                self.log.warning("kihagyott kézi bejegyzés (%s): %r", exc, entry)
                continue
            age = (today - seen).days
            if age < 0 or age > max_age:
                self.log.info("lejárt kézi ár (%s, %s) – kihagyva", merchant, seen.isoformat())
                continue
            offers.append(self.offer(
                country=country,
                merchant=merchant,
                title=str(entry.get("title") or f"{merchant} – kézzel rögzített ár"),
                price=price,
                currency=str(entry.get("currency") or COUNTRIES[country][2]),
                url=url,
                availability=f"kézi adat, {seen.isoformat()}",
                variant=str(entry.get("variant") or ""),
            ))
        return offers
