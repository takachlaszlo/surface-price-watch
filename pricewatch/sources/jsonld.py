"""Generic adapter: any shop product page that publishes schema.org JSON-LD.

config.yaml:
    - id: shop_example
      adapter: jsonld
      options:
        pages:
          - url: https://shop.example/surface-pro-11-...
            country: CH
            merchant: Example Shop
            variant: "Platin"      # optional, otherwise derived from the title
            trust_url: false       # true = skip the title check for this URL
"""
from __future__ import annotations

from ..delivery import Delivery
from ..financing import Financing, from_page
from ..http import FetchError
from ..models import COUNTRIES, Offer
from ..parse import clean, jsonld_offers, jsonld_products
from . import register
from .base import Source

_UNAVAILABLE = {"outofstock", "discontinued", "soldout"}
_USED = {"usedcondition", "refurbishedcondition", "damagedcondition"}
_AVAILABILITY_HU = {
    "instock": "raktáron",
    "instoreonly": "csak üzletben",
    "limitedavailability": "korlátozott készlet",
    "onlineonly": "csak online",
    "preorder": "előrendelhető",
    "presale": "előrendelhető",
    "backorder": "rendelésre",
    "outofstock": "nincs készleten",
}
_ID_FIELDS = ("mpn", "sku", "gtin13", "gtin", "gtin12", "gtin14", "productID")


@register("jsonld")
class JsonLdSource(Source):
    def fetch(self) -> list[Offer]:
        offers: list[Offer] = []
        errors: list[str] = []
        pages = self.options.get("pages") or []
        for page in pages:
            try:
                offers.extend(self._page(page))
            except FetchError as exc:
                if len(pages) == 1:
                    raise
                errors.append(f"{page.get('merchant', page['url'])}: {exc}")
                self.log.warning("%s: %s", page["url"], exc)
        if errors and not offers:
            raise FetchError("; ".join(errors))
        return offers

    def _page(self, page: dict) -> list[Offer]:
        url = page["url"]
        country = page["country"].upper()
        html = self.http.get_text(url)
        found: list[Offer] = []
        # Hungarian shops print their instalment plans (THM) on the product page
        financing = from_page(html) if country == "HU" else Financing()
        for product in jsonld_products(html):
            name = clean(str(product.get("name") or ""))
            ids = " ".join(str(product[k]) for k in _ID_FIELDS if isinstance(product.get(k), (str, int)))
            if not page.get("trust_url") and not self.matcher.matches(name, ids):
                continue
            for item in jsonld_offers(product):
                if (item.get("condition") or "").lower() in _USED:
                    continue
                if (item.get("availability") or "").lower() in _UNAVAILABLE and not page.get("include_unavailable"):
                    continue
                found.append(self.offer(
                    country=country,
                    merchant=page.get("merchant") or item.get("seller") or url.split("/")[2],
                    title=name or page.get("merchant", ""),
                    price=item["price"],
                    currency=item.get("currency") or page.get("currency") or COUNTRIES[country][2],
                    url=url,
                    availability=_AVAILABILITY_HU.get((item.get("availability") or "").lower(), item.get("availability")),
                    variant=page.get("variant"),
                    delivery=Delivery.from_dict(page.get("delivery")),
                    financing=financing,
                ))
        if not found:
            self.log.info("nincs rendelhető, illeszkedő ajánlat (nincs készleten vagy más termék): %s", url)
        # one page describes one product: keep its cheapest offer
        return sorted(found, key=lambda o: o.price)[:1]
