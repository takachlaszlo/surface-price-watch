"""Regressions found in the first real run on the NAS (2026-10-01)."""
from pathlib import Path

from pricewatch.config import load_config
from pricewatch.http import HttpClient
from pricewatch.matcher import Matcher
from pricewatch.models import Offer, normalize_merchant
from pricewatch.report import select_top
from pricewatch.sources import SourceContext, load_adapters
from pricewatch.sources.olcsobbat import _delivery

ROOT = Path(__file__).resolve().parents[1]


def idealo_row(price: str, logo_shop: str, button_shop: str) -> str:
    return f"""
    <li class="productOffers-listItem">
      <span class="productOffers-listItemTitleInner" title="Microsoft Surface Pro 11 CU5/16GB/256GB EU Platin W11P"></span>
      <a class="productOffers-listItemOfferPrice">{price} €</a>
      <div class="productOffers-listItemOfferShippingDetails" title="{price} € inkl. Versand"></div>
      <a class="productOffers-listItemOfferShopV2LogoLink" data-shop-name="{logo_shop}"></a>
      <a class="productOffers-listItemOfferCtaLeadout" data-shop-name="{button_shop}">Zum Shop</a>
    </li>"""


def test_idealo_marketplace_seller_is_not_booked_as_the_shop_itself():
    cfg = load_config(ROOT / "config" / "config.yaml")
    ctx = SourceContext(HttpClient(min_delay=0), Matcher(cfg.must_match, cfg.must_not_match, cfg.mpns))
    html = ("<html><head><title>Surface Pro 11 platin EP2-20112</title></head><body><h1>Microsoft Surface Pro 11 EP2-20112</h1><ul>"
            + idealo_row("1.601,99", "Amazon Marketplace - Shop aus Luxemburg", "cyberport")
            + idealo_row("1.660,39", "cyberport.de - Shop aus Dresden", "cyberport.de")
            + "</ul></body></html>")
    offers = load_adapters()["idealo"]("idealo_de", {}, ctx).parse(html, {"url": "u", "country": "DE"})
    assert [(o.merchant, o.price) for o in offers] == [("Amazon Marketplace (cyberport)", 1601.99), ("cyberport.de", 1660.39)]
    assert offers[0].merchant_key == "amazonmarketplace" and offers[1].merchant_key == "cyberport"


def test_merchant_names_from_different_comparison_sites_collapse():
    for names in [("büroshop24", "bueroshop24.de"), ("Jacob Elektronik direkt", "jacob.de"),
                  ("ARLT Computer", "arlt.com"), ("XITRA.de", "xitra24"),
                  ("CNW IT-Systeme", "c-nw.de", "Computer & NetWorks"),
                  ("Galaxus.de (Marktplatzhändler)", "galaxus"), ("Amazon Market", "Amazon Marketplace (cyberport)")]:
        assert len({normalize_merchant(n) for n in names}) == 1, names


def test_equal_prices_rank_by_known_shipping():
    cfg = load_config(ROOT / "config" / "config.yaml")

    def offer(merchant, shipping):
        return Offer("s", "DE", merchant, "Surface Pro 11", 1594.0, "EUR", "https://x.example", shipping=shipping)

    top = select_top([offer("Alternate", 7.99), offer("computeruniverse", None), offer("Easynotebooks", 0.0)], cfg)
    assert [o.merchant for o in top["DE"]] == ["Easynotebooks", "Alternate", "computeruniverse"]


def test_olcsobbat_delivery_text_is_trimmed():
    raw = "Ingyenes szállítás , 4 nap alatt Személyes átvét, Futár, PickPack, Foxpost Kártya, Utalás, Utánvét, Készpénz"
    assert _delivery(raw) == "Ingyenes szállítás, 4 nap alatt"
