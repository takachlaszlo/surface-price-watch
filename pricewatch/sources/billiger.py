"""billiger.de variant product pages – German merchants of one SKU.

robots.txt allows /products/ pages; /search, /offers/ and the /redirect
click-out are disallowed and never fetched. The page does not print the part
number, so each configured URL is trusted as SKU-specific and the shop titles
are only checked against the exclusion list.

config.yaml:
    - id: billiger
      adapter: billiger
      options:
        pages:
          - url: https://www.billiger.de/products/5185979337-microsoft-surface-pro-11-...
            variant: Platin
"""
from __future__ import annotations

import re

from ..delivery import from_german_text
from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source


@register("billiger")
class BilligerSource(Source):
    def fetch(self) -> list[Offer]:
        offers: list[Offer] = []
        for page in self.options.get("pages") or []:
            html = self.http.get_text(page["url"])
            found = self.parse(html, page)
            self.log.info("%s: %d ajánlat", page["url"], len(found))
            offers.extend(found)
        return offers

    def parse(self, html: str, page: dict) -> list[Offer]:
        doc = soup(html)
        h1 = doc.select_one("h1")
        product_title = clean(h1.get_text(" ")) if h1 else ""
        pid = re.search(r"/products/(\d+)", page["url"])
        page_pid = pid.group(1) if pid else None
        found: list[Offer] = []
        for row in doc.select("div[data-offer-row][data-offer-id]"):
            if page_pid and row.get("data-product-id") not in (None, page_pid):
                continue  # cards of sibling variants ("weitere Angebote")
            price_node = row.select_one("[data-price]")
            price = parse_price(clean(price_node.get_text(" "))) if price_node else None
            if price is None:
                continue
            merchant = ""
            shop_link = row.select_one('a[href^="/shops/"]')
            if shop_link and shop_link.get("title"):
                named = re.search(r"für (.+?) anzeigen", shop_link["title"])
                merchant = named.group(1) if named else ""
            if not merchant:
                logo = row.select_one('img[alt^="Shop "]')
                merchant = logo["alt"][5:] if logo else ""
            merchant = re.sub(r"^Verkäufer:\s*", "", merchant).strip()  # marketplace sellers
            if not merchant:
                continue
            title_node = row.select_one("div[title]")
            title = clean(title_node["title"]) if title_node else product_title
            if self.matcher.rejects(title):
                continue
            text = clean(row.get_text(" "))
            shipping_match = re.search(r"(?:ab )?([\d.]+,\d{2}) € Versand", text)
            shipping = parse_price(shipping_match.group(1)) if shipping_match else None
            if shipping_match and shipping is None:
                shipping = 0.0  # "0,00 € Versand"
            elif shipping is None and "ersandkostenfrei" in text:
                shipping = 0.0
            delivery = re.search(r"Lieferzeit: (.*?)(?: Shop-Info| Zum Anbieter|$)", text)
            found.append(self.offer(
                country="DE",
                merchant=merchant,
                title=title or product_title,
                price=price,
                currency="EUR",
                url=self.link_for(page, merchant, page["url"]),
                shipping=shipping,
                availability=delivery.group(1).strip()[:80] if delivery else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
                delivery=from_german_text(text),
            ))
        return found
