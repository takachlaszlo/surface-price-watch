import pytest

from pricewatch.parse import jsonld_offers, jsonld_products, parse_price


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1'099.–", 1099.0),
        ("CHF 1’099.00", 1099.0),
        ("1.099,00 €", 1099.0),
        ("€ 1.099,-", 1099.0),
        ("459 990 Ft", 459990.0),
        ("459.990 Ft", 459990.0),
        ("1 099,90", 1099.9),
        ("1099.9", 1099.9),
        ("ab 1.234,56 EUR", 1234.56),
        ("1,099.00", 1099.0),
        (1149, 1149.0),
        ("0", None),
        ("Preis auf Anfrage", None),
        (None, None),
    ],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Product","name":"Microsoft Surface Pro 11 Ultra 5 236V 16GB 256GB Platin","mpn":"EP2-00004",
  "offers":{"@type":"Offer","price":"1.199,00","priceCurrency":"EUR","availability":"https://schema.org/InStock",
            "url":"https://shop.example/p/1","seller":{"@type":"Organization","name":"Example Shop"}}}]}
</script>
<script type="application/ld+json">
{"@type":"Product","name":"Other","offers":{"@type":"AggregateOffer","lowPrice":"999","priceCurrency":"CHF",
 "offers":[{"@type":"Offer","price":"1049.00","priceCurrency":"CHF"},{"@type":"Offer","price":"999.00"}]}}
</script>
</head></html>
"""


def test_jsonld_products_and_offers():
    products = jsonld_products(_HTML)
    assert [p["name"] for p in products] == ["Microsoft Surface Pro 11 Ultra 5 236V 16GB 256GB Platin", "Other"]
    first = jsonld_offers(products[0])
    assert first == [{
        "price": 1199.0, "currency": "EUR", "availability": "InStock",
        "url": "https://shop.example/p/1", "seller": "Example Shop", "condition": None,
    }]
    aggregate = jsonld_offers(products[1])
    assert [(o["price"], o["currency"]) for o in aggregate] == [(1049.0, "CHF"), (999.0, "CHF")]
