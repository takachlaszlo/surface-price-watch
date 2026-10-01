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

from ..delivery import Delivery, from_carriers
from ..models import Offer, normalize_merchant
from ..parse import clean, parse_price, soup
from . import register
from .base import Source


def _shop_name(node) -> str:
    name = clean(node.get("data-shop-name")) if node else ""
    name = re.sub(r"\s+-\s+Shop aus .*$", "", name)
    return re.sub(r"\s*\(?\b(AT|DE)\)?\s*$", "", name).strip()


def _merchant(row) -> str:
    """The logo names the shop; on marketplace rows the button names the seller instead.

    "Amazon Marketplace" + seller "cyberport" must not be booked as Cyberport's own offer.
    """
    shop = _shop_name(row.select_one("a.productOffers-listItemOfferShopV2LogoLink[data-shop-name]"))
    seller = _shop_name(row.select_one("a.productOffers-listItemOfferCtaLeadout[data-shop-name]"))
    if shop and seller and normalize_merchant(shop) != normalize_merchant(seller):
        return f"{shop} ({seller})"
    return shop or seller or _shop_name(row.select_one("[data-shop-name]"))


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

    @staticmethod
    def _delivery(row, country: str) -> Delivery:
        info = from_carriers([clean(b.get_text(" ")) for b in row.select(
            ".productOffers-listItemOfferDeliveryBlock .productOffers-listItemOfferGreyBadge")])
        info.home = True  # every idealo offer is a mail-order offer, with or without carrier badges
        logo = row.select_one("a.productOffers-listItemOfferShopV2LogoLink[data-shop-name]")
        raw_name = logo.get("data-shop-name") if logo else ""
        if country == "AT" and re.search(r"\.de\b|\(AT\)", raw_name):
            # "easynotebooks.de (AT)": a German shop that ships to Austria – nothing to collect locally
            info.pickup, info.note = False, "németországi bolt, Ausztriába szállít"
        return info

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
            merchant = _merchant(row)
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
                delivery=self._delivery(row, page["country"].upper()),
            ))
        return found
