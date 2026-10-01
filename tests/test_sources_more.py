"""Adapters parsed against trimmed copies of real pages saved on 2026-09-30."""
from datetime import datetime
from pathlib import Path

import pytest

from pricewatch.config import load_config
from pricewatch.http import HttpClient
from pricewatch.matcher import Matcher
from pricewatch.models import normalize_merchant
from pricewatch.sources import SourceContext, load_adapters

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def ctx():
    cfg = load_config(ROOT / "config" / "config.yaml")  # the shipped matching rules
    return SourceContext(HttpClient(min_delay=0), Matcher(cfg.must_match, cfg.must_not_match, cfg.mpns))


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def brief(offers):
    return [(o.country, o.merchant, o.price, o.shipping) for o in offers]


def test_heise_uses_geizhals_markup_and_rejects_mismapped_ultra7_row(ctx):
    src = load_adapters()["geizhals"]("heise", {}, ctx)
    offers = src.parse(fixture("heise_offers.html"), {"url": "u", "variant": "Platin"}, {"AT", "DE"})
    # the fixture's 4th row is MediaMarkt's "Core Ultra 7 266V" listing filed under this SKU
    assert brief(offers) == [
        ("DE", "Easynotebooks.de", 1594.0, 0.0),  # GRATISVERSAND wins over the express surcharge
        ("DE", "galaxus", 1601.99, 0.0),
        ("AT", "e-tec.at", 1730.6, 0.0),
    ]


def test_olcsobbat(ctx):
    src = load_adapters()["olcsobbat"]("olcsobbat", {}, ctx)
    offers = src.parse(fixture("olcsobbat_offers.html"), {"url": "u"})
    assert brief(offers) == [("HU", "iPon", 705490.0, 0.0)]
    assert offers[0].currency == "HUF" and offers[0].variant == "Platin"
    # a page whose title has no known part number is not trusted
    assert src.parse(fixture("olcsobbat_offers.html").replace("EP2-20849", "ZIK-00006"), {"url": "u"}) == []


def test_billiger(ctx):
    src = load_adapters()["billiger"]("billiger", {}, ctx)
    offers = src.parse(fixture("billiger_offers.html"), {"url": "https://www.billiger.de/products/5185979337-x"})
    assert brief(offers) == [
        ("DE", "Easynotebooks", 1594.0, 0.0),
        ("DE", "Galaxus.de", 1601.99, 0.0),
        ("DE", "Easynotebooks", 1601.99, 0.0),  # marketplace listing, "Verkäufer:" prefix stripped
    ]
    # cards that belong to a sibling variant are ignored
    assert src.parse(fixture("billiger_offers.html"), {"url": "https://www.billiger.de/products/999-x"}) == []


def test_hardwareschotte_drops_stale_prices(ctx):
    now = datetime(2026, 9, 30, 22, 0)
    fresh = load_adapters()["hardwareschotte"]("hws", {"max_age_days": 3}, ctx)
    offers = fresh.parse(fixture("hardwareschotte_offers.html"), {"url": "u"}, now)
    assert brief(offers) == [
        ("DE", "Easynotebooks", 1594.0, None),
        ("DE", "computeruniverse", 1594.0, 6.99),
        ("DE", "Alternate", 1594.0, 7.99),
    ]
    everything = load_adapters()["hardwareschotte"]("hws", {"max_age_days": 9999}, ctx)
    stale = everything.parse(fixture("hardwareschotte_offers.html"), {"url": "u"}, now)
    assert brief(stale)[0] == ("DE", "Cyberport", 1575.4, 6.99)  # "Preis vom 05.08.2026" – weeks old


def test_idealo(ctx):
    src = load_adapters()["idealo"]("idealo_at", {}, ctx)
    page = {"url": "https://www.idealo.at/preisvergleich/OffersOfProduct/205834888_-x.html", "country": "AT"}
    offers = src.parse(fixture("idealo_offers.html"), page)
    assert brief(offers) == [
        ("AT", "easynotebooks.de", 1607.39, 9.99),
        ("AT", "cyberport.at", 1674.34, 9.99),
        ("AT", "galaxus.at", 1684.33, 0.0),
    ]
    assert all(o.variant == "Platin" and o.currency == "EUR" for o in offers)
    generic = fixture("idealo_offers.html").replace("EP2-20112", "")
    assert src.parse(generic, page) == []  # the family page (no part number) is refused


@pytest.mark.parametrize("names", [
    ("www.Galaxus.ch", "Galaxus", "galaxus.ch"),
    ("BRACK.CH AG", "Brack", "brack.ch"),
    ("Jacob Elektronik direkt", "Jacob Elektronik"),
    ("heinzsoft-shop.at", "HEINZSOFT"),
    ("Easynotebooks.de", "Easynotebooks"),
    ("computeruniverse.net", "computeruniverse"),
    ("office-partner.de", "Office-Partner"),
])
def test_merchant_names_collapse(names):
    assert len({normalize_merchant(n) for n in names}) == 1


def test_merchant_names_stay_distinct():
    assert normalize_merchant("digitec") != normalize_merchant("Galaxus")
    assert normalize_merchant("1ashop.at") != normalize_merchant("e-tec.at")
