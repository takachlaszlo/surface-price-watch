"""Microsoft Store – the public Display Catalog JSON API behind microsoft.com/…/d/… pages.

Every SKU of a product carries its Microsoft part number, so matching is done on
the MPN list of the config (never on titles). The 16 GB / 256 GB Intel SKU was
not in the DE/AT/CH catalog on 2026-09-30 (HU has no device store at all); the
adapter keeps checking daily and reports it as soon as Microsoft lists it.

config.yaml:
    - id: microsoft_store
      adapter: msstore
      options:
        big_id: 8QFMN9XP1RL9          # "Surface Pro for Business 13" (11th Edition) | Intel"
        markets:
          - {market: DE, language: de-de, merchant: Microsoft Store DE,
             url: https://www.microsoft.com/de-de/d/surface-pro-for-business-13-zoll-11-edition-intel/8qfmn9xp1rl9}
"""
from __future__ import annotations

from ..models import Offer
from . import register
from .base import Source

API = "https://displaycatalog.mp.microsoft.com/v7.0/products"


@register("msstore")
class MicrosoftStoreSource(Source):
    def fetch(self) -> list[Offer]:
        big_id = self.options["big_id"]
        offers: list[Offer] = []
        for market in self.options.get("markets") or []:
            url = f"{API}?bigIds={big_id}&market={market['market']}&languages={market['language']},neutral"
            doc = self.http.get_json(url, headers={"Accept": "application/json"})
            found = self.parse(doc, market)
            self.log.info("%s: %d ajánlat", market["market"], len(found))
            offers.extend(found)
        return offers

    def parse(self, doc: dict, market: dict) -> list[Offer]:
        found: list[Offer] = []
        for product in doc.get("Products") or []:
            for dsa in product.get("DisplaySkuAvailabilities") or []:
                sku = dsa.get("Sku") or {}
                mpn = ((sku.get("Properties") or {}).get("InventoryControlSkuId") or "").strip()
                localized = (sku.get("LocalizedProperties") or [{}])[0]
                title = (localized.get("SkuTitle") or product.get("LocalizedProperties", [{}])[0].get("ProductTitle") or "").strip()
                if not mpn or not self.matcher.matches(title, mpn) or not self.matcher.find_mpn(mpn):
                    continue
                for availability in dsa.get("Availabilities") or []:
                    price = ((availability.get("OrderManagementData") or {}).get("Price") or {})
                    if price.get("ListPrice") is None or float(price["ListPrice"]) <= 0:
                        continue
                    actions = availability.get("Actions") or []
                    if "Purchase" not in actions and not self.options.get("include_unavailable"):
                        continue
                    found.append(self.offer(
                        country=market["market"],
                        merchant=market.get("merchant") or f"Microsoft Store {market['market']}",
                        title=f"{title} ({mpn})",
                        price=float(price["ListPrice"]),
                        currency=price.get("CurrencyCode") or "EUR",
                        url=market["url"],
                        shipping=0.0,
                        availability="megvásárolható",
                    ))
                    break  # one availability per SKU is enough
        return found
