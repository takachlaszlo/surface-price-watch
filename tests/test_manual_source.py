from datetime import date

import pytest

from pricewatch.http import FetchError, HttpClient
from pricewatch.matcher import Matcher
from pricewatch.sources import SourceContext, load_adapters


def make(options):
    return load_adapters()["manual"]("kezi_arak", options, SourceContext(HttpClient(min_delay=0), Matcher()))


def test_fresh_entries_are_used_and_stale_or_broken_ones_dropped():
    entries = [
        {"merchant": "Galaxus", "country": "ch", "price": "1'499.–", "variant": "Platin",
         "url": "https://www.galaxus.ch/de/s1/product/54161673", "date": date(2026, 9, 28)},
        {"merchant": "digitec", "country": "CH", "price": 1515, "url": "https://www.digitec.ch/x", "date": "2026-09-20"},
        {"merchant": "Holnap", "country": "CH", "price": 1, "url": "https://x.example", "date": "2026-10-05"},
        {"merchant": "Hiányos", "country": "CH", "url": "https://x.example", "date": "2026-10-01"},
    ]
    offers = make({"max_age_days": 7}).parse(entries, date(2026, 10, 1))
    assert [(o.merchant, o.country, o.price, o.currency, o.variant) for o in offers] == [("Galaxus", "CH", 1499.0, "CHF", "Platin")]
    assert offers[0].availability == "kézi adat, 2026-09-28"


def test_file_handling(tmp_path):
    assert make({"file": str(tmp_path / "nincs.yaml")}).fetch() == []
    empty = tmp_path / "ures.yaml"
    empty.write_text("# csak megjegyzés\n", encoding="utf-8")
    assert make({"file": str(empty)}).fetch() == []
    broken = tmp_path / "hibas.yaml"
    broken.write_text("merchant: [Galaxus\n", encoding="utf-8")
    with pytest.raises(FetchError):
        make({"file": str(broken)}).fetch()
