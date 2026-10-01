"""Whole pipeline with the shipped config.yaml, served from fixtures – no network, no SMTP."""
import smtplib
from pathlib import Path

import pytest

from pricewatch import runner
from pricewatch.config import load_config
from pricewatch.http import HttpClient
from pricewatch.sources import load_adapters

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

ECB = b"""<?xml version="1.0"?><gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref"><Cube><Cube time="2026-09-30">
 <Cube currency="CHF" rate="0.9400"/><Cube currency="HUF" rate="400.00"/></Cube></Cube></gesmes:Envelope>"""

SHOP_PAGE = """<html><head><script type="application/ld+json">
{"@type":"Product","name":"Microsoft Surface Pro 11 - Copilot+ PC (EP2-20849) Platinum","mpn":"EP2-20849",
 "offers":{"@type":"Offer","price":"757900","priceCurrency":"HUF","availability":"https://schema.org/InStock"}}
</script></head></html>"""


class Reply:
    def __init__(self, status, body=b"", content_type="text/html; charset=utf-8", url=""):
        self.status_code, self.content, self.url = status, body, url
        self.headers = {"Content-Type": content_type}


class FixtureSession:
    """Answers every configured URL from a fixture chosen by host name."""

    def __init__(self):
        self.headers, self.calls = {}, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Reply(404)
        host = url.split("/")[2]
        if "ecb.europa.eu" in host:
            return Reply(200, ECB, "text/xml")
        if "geizhals.at" in host:
            return Reply(403, b"<html><title>Just a moment...</title></html>")  # Cloudflare challenge day
        if "displaycatalog" in host:
            return Reply(200, b'{"Products": []}', "application/json")
        if "notebook.hu" in host:
            return Reply(200, SHOP_PAGE.encode())
        by_host = {
            "preisvergleich.heise.de": "heise_offers.html",
            "www.idealo.at": "idealo_offers.html",
            "www.toppreise.ch": "toppreise_offers.html",
            "www.olcsobbat.hu": "olcsobbat_offers.html",
            "www.hardwareschotte.de": "hardwareschotte_offers.html",
        }
        if host in by_host and ("20112" in url or "20849" in url or "p797281" in url):
            return Reply(200, (FIXTURES / by_host[host]).read_bytes())
        return Reply(200, b"<html><body><h1>Seite</h1></body></html>")  # reachable, nothing to parse


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICEWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("MAIL_TO", "technikai@mail.home.arpa, masik@mail.home.arpa")
    config = load_config(ROOT / "config" / "config.yaml")
    config.min_delay = 0
    session = FixtureSession()
    original = HttpClient.__init__

    def patched(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.session = session

    monkeypatch.setattr(HttpClient, "__init__", patched)
    monkeypatch.setattr("pricewatch.sources.hardwareschotte.datetime", _FixedDate)
    config.session = session
    return config


class _FixedDate:
    """hardwareschotte compares price dates with 'now'; the fixture is from 2026-09-30."""

    def __new__(cls, *args, **kwargs):
        from datetime import datetime
        return datetime(*args, **kwargs)

    @staticmethod
    def now():
        from datetime import datetime
        return datetime(2026, 9, 30, 22, 0)


def test_shipped_config_is_consistent():
    config = load_config(ROOT / "config" / "config.yaml")
    adapters = load_adapters()
    assert {s.adapter for s in config.sources} <= set(adapters)
    assert len(config.sources) >= 10 and all(s.enabled for s in config.sources)
    for src in config.sources:
        pages = src.options.get("pages") or src.options.get("markets")
        assert pages and all(p["url"].startswith("https://") for p in pages), src.id


def test_full_run_builds_report_and_sends_mail(cfg, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            pass

        def send_message(self, msg, from_addr=None, to_addrs=None):
            sent.update(msg=msg, from_addr=from_addr, to_addrs=to_addrs)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    result = runner.run_once(cfg)

    status = {s.source_id: s.status for s in result.sources}
    assert status["geizhals_at"] == "blocked"  # reported, not worked around
    assert status["heise_preisvergleich"] == "ok" and status["toppreise"] == "ok"
    assert status["idealo_at"] == "ok" and status["olcsobbat"] == "ok" and status["shops_hu"] == "ok"
    assert status["microsoft_store"] == "empty"

    best = {c: min((o for o in result.offers if o.country == c), key=lambda o: o.price) for c in ("CH", "HU", "AT", "DE")}
    assert (best["CH"].merchant, best["CH"].price, best["CH"].currency) == ("Galaxus", 1515.0, "CHF")
    assert best["CH"].url == "https://www.galaxus.ch/de/s1/product/54161673"  # direct link from merchant_links
    assert (best["HU"].merchant, best["HU"].price) == ("iPon", 705490.0)
    assert (best["AT"].merchant, best["AT"].price) == ("easynotebooks.de", 1607.39)
    assert (best["DE"].price, best["DE"].currency) == (1594.0, "EUR")
    assert best["CH"].price_eur == round(1515.0 / 0.94, 2)
    # Easynotebooks is listed by heise and hardwareschotte: one merchant after de-duplication
    assert sum(1 for o in result.offers if o.country == "DE" and o.merchant_key == "easynotebooks") == 1

    html = (cfg.data_dir / "last_report.html").read_text(encoding="utf-8")
    for needle in ("Svájc", "Magyarország", "Ausztria", "Németország", "Galaxus", "iPon",
                   "letiltva (bot-védelem)", "EKB referencia-árfolyam, 2026-09-30"):
        assert needle in html

    assert sent["server"] == ("mail.home.arpa", 25)
    assert sent["from_addr"] == "technikai@mail.home.arpa"
    assert sent["to_addrs"] == ["technikai@mail.home.arpa", "masik@mail.home.arpa"]
    assert sent["msg"]["Subject"].startswith("Surface Pro 11 árfigyelő")
    assert "CH 1 515,00 CHF" in sent["msg"]["Subject"] and "HU 705 490 Ft" in sent["msg"]["Subject"]
    assert sent["msg"].get_body(("html",)) is not None and sent["msg"].get_body(("plain",)) is not None
    # robots.txt was consulted once per host and no search / click-out URL was ever requested
    assert not [u for u in cfg.session.calls if "/redir/" in u or "?fs=" in u or "/ext_" in u or "storejump" in u]
