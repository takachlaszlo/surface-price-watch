"""Geizhals product pages (geizhals.at with hloc=at&hloc=de, or heise.de/preisvergleich).

One product page lists every Austrian and German merchant; the merchant's
country is the flag next to its name. robots.txt allows product pages but not
the search (`/?fs=`) or the click-out redirects, so the report links to the
Geizhals page and the merchant deep link is only carried as a redirect URL.

config.yaml:
    - id: geizhals
      adapter: geizhals
      options:
        pages:
          - url: https://geizhals.at/microsoft-surface-pro-11-ep2-20112-a3408236.html?hloc=at&hloc=de
            variant: Platin
        countries: [AT, DE]          # keep offers of these merchant countries
        trust_pages: true            # the page is SKU-specific: no title check needed
"""
from __future__ import annotations

import re

from ..delivery import from_german_text
from ..models import Offer
from ..parse import clean, parse_price, soup
from . import register
from .base import Source

_FLAG_COUNTRY = {"at": "AT", "de": "DE", "österreich": "AT", "deutschland": "DE"}


@register("geizhals")
class GeizhalsSource(Source):
    def fetch(self) -> list[Offer]:
        offers: list[Offer] = []
        countries = {c.upper() for c in self.options.get("countries", ["AT", "DE"])}
        for page in self.options.get("pages") or []:
            html = self.http.get_text(page["url"])
            found = self.parse(html, page, countries)
            self.log.info("%s: %d ajánlat", page["url"], len(found))
            offers.extend(found)
        return offers

    def parse(self, html: str, page: dict, countries: set[str]) -> list[Offer]:
        doc = soup(html)
        product_title = clean(doc.select_one("h1").get_text()) if doc.select_one("h1") else ""
        trust = self.options.get("trust_pages", True)
        found: list[Offer] = []
        for row in doc.select("div.offer"):
            price = parse_price(clean(row.select_one(".gh_price").get_text()) if row.select_one(".gh_price") else None)
            merchant_node = row.select_one("[data-merchant-name]")
            if price is None or merchant_node is None:
                continue
            flag = row.select_one(".offer__merchant img[alt]")
            country = _FLAG_COUNTRY.get((flag.get("alt") or "").strip().lower(), "") if flag else ""
            # "Easynotebooks.de (AT)" = a German shop's offer for Austrian customers
            market = re.search(r"\((AT|DE)\)\s*$", merchant_node["data-merchant-name"])
            if market:
                country = market.group(1)
            if country not in countries:
                continue
            details = row.select_one(".offer__details > div")
            title = clean(details.get_text(" ")) if details else product_title
            if not trust and not self.matcher.matches(title):
                continue
            if self.matcher.rejects(title):
                continue
            classes = " ".join(row.get("class") or [])
            if "offer--unavailable" in classes and not self.options.get("include_unavailable"):
                continue
            delivery = row.select_one(".offer__delivery-time")
            payment = row.select_one(".offer__delivery-payment")
            how = from_german_text(clean(payment.get_text(" ")) if payment else "",
                                   clean(delivery.get_text(" ")) if delivery else "", silence_means_no=True)
            if market and market.group(1) == "AT" and flag is not None and (flag.get("alt") or "").upper() == "DE":
                # "Easynotebooks.de (AT)": a German shop that ships to Austria – nothing to collect locally
                how.pickup, how.pickup_note, how.note = False, "", "németországi bolt, Ausztriába szállít"
            merchant = re.sub(r"\s*\((AT|DE)\)\s*$", "", merchant_node["data-merchant-name"])
            found.append(self.offer(
                country=country,
                merchant=merchant,
                title=title or product_title,
                price=price,
                currency="EUR",
                url=self.link_for(page, merchant, page["url"]),
                shipping=_shipping(row),
                availability=clean(delivery.get_text(" "))[:80] if delivery else None,
                variant=page.get("variant") or self.matcher.variant_label(product_title, title),
                delivery=how,
            ))
        return found


def _shipping(row) -> float | None:
    pay = row.select_one(".offer__delivery-payment")
    if pay is None:
        return None
    if "GRATISVERSAND" in clean(pay.get_text(" ")).upper():
        return 0.0  # later .gh_extracost entries are surcharges (express, cash on delivery)
    extra = pay.select_one(".gh_extracost")
    return parse_price(clean(extra.get_text())) if extra is not None else None
