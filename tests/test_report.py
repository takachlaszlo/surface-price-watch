from datetime import datetime
from pathlib import Path

from pricewatch.config import Config, MailConfig, ScheduleConfig
from pricewatch.models import Offer, RunResult, SourceResult
from pricewatch.report import build_report, fmt_money, select_top, sparkline
from pricewatch.runner import dedupe
from pricewatch.storage import Storage


def make_cfg(tmp_path: Path) -> Config:
    return Config(
        product_name="Surface Pro 11", must_match=[], must_not_match=[], mpns=[], price_limits={},
        countries=["CH", "HU", "AT", "DE"], top_n=3, distinct_merchants=True, rank_by="price",
        fallback_fx={}, user_agent="x", min_delay=0, timeout=5, respect_robots=True, sources=[],
        data_dir=tmp_path,
        mail=MailConfig("h", 25, "none", "", "", False, "a@b", ["a@b"], "n"),
        schedule=ScheduleConfig("07:00", False, True),
    )


def offer(country, merchant, price, currency, variant="", source="s") -> Offer:
    eur = {"CHF": 0.94, "HUF": 400, "EUR": 1}
    return Offer(source, country, merchant, f"Surface Pro 11 {variant}", price, currency,
                 f"https://{merchant.lower()}.example/p", variant=variant, price_eur=round(price / eur[currency], 2))


def test_fmt_money():
    assert fmt_money(1099, "CHF") == "1 099,00 CHF"
    assert fmt_money(459990, "HUF") == "459 990 Ft"
    assert fmt_money(1049.5, "EUR") == "1 049,50 €"


def test_sparkline():
    assert sparkline([1, 2, 3]) == "▁▅█"
    assert sparkline([5, 5]) == "▄▄"
    assert sparkline([]) == ""


def test_dedupe_keeps_cheapest_per_merchant_and_variant():
    offers = [offer("DE", "Cyberport", 1099, "EUR", source="geizhals"),
              offer("DE", "cyberport.de", 1089, "EUR", source="idealo"),
              offer("DE", "Cyberport", 1200, "EUR", "OLED")]
    kept = dedupe(offers)
    assert sorted((o.price, o.source) for o in kept) == [(1089, "idealo"), (1200, "s")]


def test_select_top_distinct_merchants():
    cfg = make_cfg(Path("."))
    offers = [offer("CH", "Galaxus", 999, "CHF"), offer("CH", "Galaxus", 1010, "CHF", "OLED"),
              offer("CH", "Brack", 1020, "CHF"), offer("CH", "Digitec", 1030, "CHF"),
              offer("CH", "Fust", 1040, "CHF")]
    top = select_top(offers, cfg)
    assert [o.merchant for o in top["CH"]] == ["Galaxus", "Brack", "Digitec"]
    assert top["HU"] == []


def test_build_report_with_history(tmp_path):
    cfg = make_cfg(tmp_path)
    storage = Storage(tmp_path)
    # yesterday's run
    run1 = storage.start_run(datetime(2026, 9, 29, 7, 0))
    storage.finish_run(run1, datetime(2026, 9, 29, 7, 5),
                       [offer("CH", "Galaxus", 1049, "CHF"), offer("DE", "Cyberport", 1120, "EUR")],
                       [SourceResult("s", "ok", 2)])
    storage.mark_mailed(run1)
    # today's run
    run2 = storage.start_run(datetime(2026, 9, 30, 7, 0))
    today = [offer("CH", "Galaxus", 999, "CHF"), offer("CH", "Brack", 1020, "CHF"),
             offer("DE", "Cyberport", 1120, "EUR"), offer("HU", "Alza", 459990, "HUF")]
    sources = [SourceResult("s", "ok", 4), SourceResult("blocked_one", "blocked", 0, "HTTP 403")]
    storage.finish_run(run2, datetime(2026, 9, 30, 7, 5), today, sources)
    result = RunResult(run2, "2026-09-30", today, sources, {"EUR": 1, "CHF": 0.94, "HUF": 400}, "teszt")

    subject, html, text = build_report(result, cfg, storage)
    assert subject.startswith("Surface Pro 11 árfigyelő 2026-09-30: CH 999,00 CHF | HU 459 990 Ft | AT – | DE 1 120,00 €")
    assert "▼ −50,00 CHF (−4,8%)" in html  # Galaxus dropped from 1049 to 999
    assert "▼ −50,00 CHF (−4,8%)" in text
    assert "változatlan" in html  # Cyberport unchanged
    assert "új" in html  # Brack was not seen yesterday
    assert "Ma nem találtam megfelelő ajánlatot" in html  # Austria empty
    assert "letiltva (bot-védelem)" in html and "HTTP 403" in html
    assert "https://galaxus.example/p" in html and "Alza" in text
    assert storage.all_time_low("CH") == (999.0, "2026-09-30", "Galaxus")
    assert storage.has_completed_run_on("2026-09-29") and not storage.has_completed_run_on("2026-09-30")
    storage.close()
