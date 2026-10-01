from pricewatch.http import HttpClient
from pricewatch.matcher import Matcher
from pricewatch.sources import SourceContext, load_adapters


def sku(mpn, title, price, actions=("Purchase",)):
    return {
        "Sku": {"SkuId": mpn, "Properties": {"InventoryControlSkuId": mpn},
                "LocalizedProperties": [{"SkuTitle": title}]},
        "Availabilities": [{"Actions": list(actions),
                            "OrderManagementData": {"Price": {"ListPrice": price, "CurrencyCode": "CHF"}}}],
    }


DOC = {"Products": [{"LocalizedProperties": [{"ProductTitle": "Surface Pro for Business 13\" (11. Edition) | Intel"}],
                     "DisplaySkuAvailabilities": [
                         sku("EP2-20180", "Intel Core Ultra 5, 32 GB, 512 GB, Platin", 2099.0),
                         sku("EP2-20112", "Intel Core Ultra 5, 16 GB, 256 GB, Platin", 1499.0),
                         sku("EP2-20095", "Intel Core Ultra 5, 16 GB, 256 GB, Schwarz", 1499.0, actions=("Details",)),
                     ]}]}


def test_msstore_matches_on_mpn_and_purchasability():
    matcher = Matcher([r"surface"], [r"512\s*GB"], ["EP2-20112", "EP2-20095"])
    src = load_adapters()["msstore"]("ms", {"big_id": "X"}, SourceContext(HttpClient(min_delay=0), matcher))
    market = {"market": "CH", "language": "de-ch", "merchant": "Microsoft Store CH", "url": "https://ms.example/ch"}
    offers = src.parse(DOC, market)
    assert [(o.merchant, o.price, o.currency, o.country) for o in offers] == [("Microsoft Store CH", 1499.0, "CHF", "CH")]
    assert "EP2-20112" in offers[0].title and offers[0].variant == "Platin"
    src.options["include_unavailable"] = True
    assert len(src.parse(DOC, market)) == 2
