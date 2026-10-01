import pytest

from pricewatch.http import BlockedError, FetchError, HttpClient
from pricewatch.matcher import Matcher
from pricewatch.sources import SourceContext, load_adapters

PAGE = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product",
 "name":"Microsoft Surface Pro 11 Ultra 5 236V 16GB 256GB Platin","mpn":"EP2-20112",
 "offers":{"@type":"Offer","price":"1.599,00","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}
</script></head><body></body></html>
"""
OTHER = PAGE.replace("Ultra 5 236V 16GB 256GB", "Ultra 7 268V 32GB 512GB").replace("EP2-20112", "EP2-20050")


class FakeHttp(HttpClient):
    def __init__(self, pages):
        super().__init__(min_delay=0)
        self.pages = pages

    def get_text(self, url, **kwargs):
        result = self.pages[url]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def ctx():
    matcher = Matcher([r"surface\s*pro", r"ultra\s*5", r"16\s*GB", r"256\s*GB"], [r"ultra\s*7|512\s*GB"], ["EP2-20112"])
    return matcher


def make(pages, ctx, options):
    http = FakeHttp(pages)
    return load_adapters()["jsonld"]("shop", options, SourceContext(http, ctx))


def test_jsonld_offer_extracted_and_wrong_product_rejected(ctx):
    pages = {"https://a.example/p": PAGE, "https://b.example/p": OTHER}
    src = make(pages, ctx, {"pages": [
        {"url": "https://a.example/p", "country": "DE", "merchant": "Shop A"},
        {"url": "https://b.example/p", "country": "DE", "merchant": "Shop B"},
    ]})
    offers = src.fetch()
    assert [(o.merchant, o.price, o.currency, o.country, o.variant) for o in offers] == [("Shop A", 1599.0, "EUR", "DE", "Platin")]
    assert offers[0].availability == "raktáron" and offers[0].url == "https://a.example/p"


def test_jsonld_partial_failure_keeps_other_pages(ctx):
    pages = {"https://a.example/p": PAGE, "https://b.example/p": BlockedError("HTTP 403")}
    src = make(pages, ctx, {"pages": [
        {"url": "https://a.example/p", "country": "AT", "merchant": "Shop A"},
        {"url": "https://b.example/p", "country": "AT", "merchant": "Shop B"},
    ]})
    assert [o.merchant for o in src.fetch()] == ["Shop A"]


def test_jsonld_all_pages_failing_raises(ctx):
    src = make({"https://b.example/p": BlockedError("HTTP 403")}, ctx,
               {"pages": [{"url": "https://b.example/p", "country": "AT", "merchant": "Shop B"}]})
    with pytest.raises(FetchError):
        src.fetch()
