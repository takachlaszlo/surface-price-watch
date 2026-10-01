from pathlib import Path

import pytest

from pricewatch.http import HttpClient
from pricewatch.matcher import Matcher
from pricewatch.sources import SourceContext, load_adapters

FIXTURES = Path(__file__).parent / "fixtures"
MUST_NOT = [r"gebraucht|refurbished|b-ware|messeware|\bEP2-\d{5}-B\b", r"\b(512|1000)\s*GB\b|\b[12]\s*TB\b"]


@pytest.fixture
def ctx():
    return SourceContext(HttpClient(), Matcher([r"surface\s*pro"], MUST_NOT, ["EP2-20112", "EP2-20095"]))


def test_geizhals_parse(ctx):
    adapters = load_adapters()
    src = adapters["geizhals"]("geizhals", {"countries": ["AT", "DE"]}, ctx)
    html = (FIXTURES / "geizhals_offers.html").read_text(encoding="utf-8")
    page = {"url": "https://geizhals.at/x-a3408236.html?hloc=at&hloc=de", "variant": "Platin"}
    offers = src.parse(html, page, {"AT", "DE"})
    assert [(o.country, o.merchant, o.price, o.shipping) for o in offers] == [
        ("DE", "Notebook.de", 1594.01, 9.99),
        ("AT", "computeruniverse.at", 1607.4, 9.99),
        ("AT", "galaxus.at", 1684.33, 0.0),
    ]  # the fourth fixture row is "offer--unavailable" and must be skipped
    assert all(o.currency == "EUR" and o.variant == "Platin" and o.url == page["url"] for o in offers)
    assert "EP2-20112" in offers[0].title
    only_at = src.parse(html, page, {"AT"})
    assert {o.country for o in only_at} == {"AT"}
    with_unavailable = adapters["geizhals"]("g", {"include_unavailable": True}, ctx).parse(html, page, {"AT", "DE"})
    assert len(with_unavailable) == 4


def test_toppreise_parse(ctx):
    adapters = load_adapters()
    html = (FIXTURES / "toppreise_offers.html").read_text(encoding="utf-8")
    page = {"url": "https://www.toppreise.ch/x-p797281", "variant": "Fekete"}
    offers = adapters["toppreise"]("toppreise", {}, ctx).parse(html, page)
    # BRACK ("im Moment nicht lieferbar") and Buchmann ("auf Anfrage") are skipped;
    # Galaxus and digitec are ordinary merchants here – this is the route to their prices
    assert [(o.merchant, o.price) for o in offers] == [("Galaxus", 1515.0), ("digitec", 1515.0)]
    assert all(o.country == "CH" and o.currency == "CHF" and o.variant == "Fekete" for o in offers)
    assert offers[0].availability.startswith("ab eigenem Lager")
    everything = adapters["toppreise"]("t", {"include_unavailable": True}, ctx).parse(html, page)
    assert [(o.merchant, o.price) for o in everything][:2] == [("BRACK.CH AG", 1415.0), ("Buchmann", 1512.35)]
