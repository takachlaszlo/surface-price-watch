"""Toppreise.ch product pages – every Swiss merchant of one SKU on one page.

Galaxus and digitec are listed here as ordinary merchants, so this is the
route to their prices (galaxus.ch itself refuses automated clients).
robots.txt only disallows the /ext_* click-out redirects, which are never
fetched; the merchant redirect is kept only as a link for the reader.

config.yaml:
    - id: toppreise
      adapter: toppreise
      options:
        pages:
          - url: https://www.toppreise.ch/preisvergleich/Tablets/...-EP2-20112-p797280
            variant: Platin
        price: product           # product = item price, total = cheapest price incl. shipping
"""
from __future__ import annotations

from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source

_UNAVAILABLE = ("nicht lieferbar", "auf anfrage", "nicht verfügbar")


@register("toppreise")
class ToppreiseSource(Source):
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
        product_title = clean(h1.get_text()) if h1 else ""
        use_total = self.options.get("price") == "total"
        found: list[Offer] = []
        for row in doc.select("div.Plugin_Offer"):
            product_price = row.select_one(".priceContainer.productPrice .Plugin_Price")
            total_price = row.select_one(".priceContainer.shippingPrice .Plugin_Price")
            price = parse_price(clean(product_price.get_text()) if product_price else None)
            total = parse_price(clean(total_price.get_text()) if total_price else None)
            if price is None:
                continue
            logo = row.select_one(".Plugin_ShopLogo img[alt]")
            name = row.select_one("a.offer-name")
            title = clean(name.get_text(" ")) if name else product_title
            if self.matcher.rejects(title):
                continue
            avail_node = row.select_one(".AbstractTooltip_AvailabilityInformationTooltip")
            availability = clean(avail_node.get("title")) if avail_node else None
            if availability and not self.options.get("include_unavailable") \
                    and any(marker in availability.lower() for marker in _UNAVAILABLE):
                continue
            shipping_node = row.select_one(".priceContainer.productPrice .shippingText")
            shipping = parse_price(clean(shipping_node.get_text())) if shipping_node else None
            if total is not None and price is not None and abs(total - price) < 0.005:
                shipping = 0.0
            merchant = (logo.get("alt") if logo else None) or "ismeretlen kereskedő"
            found.append(self.offer(
                country="CH",
                merchant=merchant,
                title=title,
                price=total if use_total and total else price,
                currency="CHF",
                url=self.link_for(page, merchant, page["url"]),
                shipping=shipping,
                availability=availability[:80] if availability else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
            ))
        return found
