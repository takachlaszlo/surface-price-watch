"""idealo variant pages (idealo.at / idealo.de) – offers of one SKU.

robots.txt allows /preisvergleich/OffersOfProduct/ pages; the search
(MainSearchProductCategory) and click-outs are disallowed and never fetched.
idealo.at lists Austrian shops plus German shops that deliver to Austria, so
every offer of a page belongs to the page's country.

config.yaml:
    - id: idealo_at
      adapter: idealo
      options:
        pages:
          - url: https://www.idealo.at/preisvergleich/OffersOfProduct/205834888_-...-ep2-20112-microsoft.html
            country: AT
            variant: Platin
"""
from __future__ import annotations

import re

from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source


@register("idealo")
class IdealoSource(Source):
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
        # a variant page names its part number; the generic family page must not be used
        if not self.matcher.find_mpn(product_title) and not self.matcher.find_mpn(doc.title.get_text() if doc.title else ""):
            self.log.warning("nem változat-oldal (nincs ismert cikkszám a címben): %s", product_title[:80])
            return []
        found: list[Offer] = []
        for row in doc.select("li.productOffers-listItem"):
            price_node = row.select_one(".productOffers-listItemOfferPrice")
            price = parse_price(clean(price_node.get_text(" "))) if price_node else None
            if price is None:
                continue
            shop = row.select_one("a.productOffers-listItemOfferCtaLeadout[data-shop-name]") \
                or row.select_one("[data-shop-name]")
            merchant = clean(shop.get("data-shop-name")) if shop else ""
            merchant = re.sub(r"\s+-\s+Shop aus .*$", "", merchant)
            merchant = re.sub(r"\s*\(?\b(AT|DE)\)?\s*$", "", merchant).strip()
            if not merchant:
                continue
            title_node = row.select_one(".productOffers-listItemTitleInner")
            title = clean((title_node.get("title") or title_node.get_text(" ")).replace("­", "")) if title_node else product_title
            if self.matcher.rejects(title):
                continue
            total_node = row.select_one(".productOffers-listItemOfferShippingDetails")
            total = parse_price(clean(total_node.get("title") or total_node.get_text(" "))) if total_node else None
            shipping = round(total - price, 2) if total is not None and total >= price else None
            delivery = row.select_one(".productOffers-listItemOfferDeliveryStatusDatesRange")
            found.append(self.offer(
                country=page["country"],
                merchant=merchant,
                title=title or product_title,
                price=price,
                currency="EUR",
                url=self.link_for(page, merchant, page["url"]),
                shipping=shipping,
                availability=("Lieferung " + clean(delivery.get_text(" ")))[:80] if delivery else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
            ))
        return found
