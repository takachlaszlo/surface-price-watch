"""Olcsóbbat.hu product pages – Hungarian merchants of one SKU.

The market leaders (Árukereső, ÁrGép) answer automated clients with a
Cloudflare challenge, so this is the Hungarian comparison site that can be read.
Product pages are robots-allowed; the /storejump.php click-out is not and is
never fetched.

config.yaml:
    - id: olcsobbat
      adapter: olcsobbat
      options:
        pages:
          - url: https://www.olcsobbat.hu/termek/...ep2_20849-67d51313e2e6c08dec0bb48f/
            variant: Platin
"""
from __future__ import annotations

import re

from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source


def _delivery(text: str) -> str:
    """'Ingyenes szállítás , 4 nap alatt Személyes átvét, Futár … Kártya' -> the delivery part only."""
    head = re.split(r"\s+(?=Személyes|Futár|PickPack|Foxpost|Kártya|Utalás|Utánvét|Készpénz)", text)[0]
    return re.sub(r"\s+,", ",", head)[:80]


@register("olcsobbat")
class OlcsobbatSource(Source):
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
        h1 = doc.select_one('h1[itemprop="name"]') or doc.select_one("h1")
        product_title = clean(h1.get_text(" ")) if h1 else ""
        # the page is trusted only if its own title carries one of the configured part numbers
        if not self.matcher.find_mpn(product_title) or self.matcher.rejects(product_title):
            self.log.warning("váratlan terméklap (nincs ismert cikkszám a címben): %s", product_title[:80])
            return []
        found: list[Offer] = []
        for item in doc.select(".offerList li.item"):
            price_node = item.select_one(".priceColumn")
            price = parse_price(clean(price_node.get_text(" "))) if price_node else None
            if price is None:
                continue
            name = item.select_one("a.offerName")
            title = clean(name.get_text(" ")) if name else product_title
            if self.matcher.rejects(title):
                continue
            shop = item.select_one(".buttonColumn .shopName2")
            logo = item.select_one(".shoplogo img[alt]")
            merchant = (clean(shop.get_text()) if shop else "") or (logo.get("alt") if logo else "")
            if not merchant:
                continue
            availability = item.select_one(".availability")
            found.append(self.offer(
                country="HU",
                merchant=merchant,
                title=title or product_title,
                price=price,
                currency="HUF",
                url=page["url"],
                shipping=0.0 if item.select_one(".availability .freeShipping") else None,
                availability=_delivery(clean(availability.get_text(" "))) if availability else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
            ))
        return found
