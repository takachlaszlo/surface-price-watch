"""hardwareschotte.de product pages – a further German comparison portal.

Its price list carries the date of every price ("Preis vom 05.08.2026"), and
some rows are weeks old. Stale rows would falsify the "cheapest offer", so
only prices not older than `max_age_days` are kept.

config.yaml:
    - id: hardwareschotte
      adapter: hardwareschotte
      options:
        max_age_days: 3
        pages:
          - url: https://www.hardwareschotte.de/preisvergleich/Microsoft-Surface-Pro-11-...-EP2-20112-p22305179
            variant: Platin
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source


@register("hardwareschotte")
class HardwareschotteSource(Source):
    def fetch(self) -> list[Offer]:
        offers: list[Offer] = []
        for page in self.options.get("pages") or []:
            html = self.http.get_text(page["url"])
            found = self.parse(html, page, datetime.now())
            self.log.info("%s: %d ajánlat", page["url"], len(found))
            offers.extend(found)
        return offers

    def parse(self, html: str, page: dict, now: datetime) -> list[Offer]:
        doc = soup(html)
        h1 = doc.select_one("h1")
        product_title = clean(h1.get_text(" ")) if h1 else ""
        oldest = now - timedelta(days=float(self.options.get("max_age_days", 3)))
        found: list[Offer] = []
        for row in doc.select("table.ol tr"):
            price_cell = row.select_one("td.ol-price")
            price_node = price_cell.select_one("button span") if price_cell else None
            price = parse_price(clean(price_node.get_text(" "))) if price_node else None
            dealer = row.select_one("td.ol-dealer button span")
            if price is None or dealer is None:
                continue
            stamp = row.select_one("td.ol-info .currentness")
            seen = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", clean(stamp.get_text()) if stamp else "")
            if not seen:
                continue  # no date -> cannot tell whether the price is current
            price_date = datetime(int(seen.group(3)), int(seen.group(2)), int(seen.group(1)))
            if price_date < oldest.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            description = row.select_one("td.ol-info .description")
            title = clean(description.get_text(" ")) if description else product_title
            if self.matcher.rejects(title):
                continue
            shipping_node = price_cell.select_one(".ol-price-deliverydetails")
            shipping_text = clean(shipping_node.get_text(" ")) if shipping_node else ""
            shipping = parse_price(shipping_text)
            if shipping is None and re.search(r"kostenlos|frei|gratis", shipping_text, re.I):
                shipping = 0.0
            status = row.select_one("td.ol-deliveryStatus div[title]")
            found.append(self.offer(
                country="DE",
                merchant=clean(dealer.get_text(" ")),
                title=title or product_title,
                price=price,
                currency="EUR",
                url=page["url"],
                shipping=shipping,
                availability=status["title"].replace("Lieferstatus: ", "")[:80] if status else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
            ))
        return found
