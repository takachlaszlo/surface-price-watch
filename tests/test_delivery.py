from pathlib import Path

from pricewatch.config import load_config
from pricewatch.delivery import Delivery, from_carriers, from_german_text, from_hungarian_text
from pricewatch.http import HttpClient
from pricewatch.matcher import Matcher
from pricewatch.models import Offer
from pricewatch.runner import dedupe
from pricewatch.sources import SourceContext, load_adapters
from pricewatch.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_german_listing_text():
    alternate = from_german_text("Vorkasse, PayPal € 7,99 . Abholung im Ladengeschäft nach Online-Bestellung möglich "
                                 "(D-35440 Linden) Lieferung in weitere Länder auf Anfrage.", silence_means_no=True)
    assert (alternate.home, alternate.pickup, alternate.pickup_note) == (True, True, "D-35440 Linden")
    galaxus = from_german_text("Kreditkarte, PayPal GRATISVERSAND . Lieferung nur innerhalb Österreichs.", silence_means_no=True)
    assert (galaxus.pickup, galaxus.note) == (False, "csak Ausztrián belül szállít")
    chain = from_german_text("Vorkasse € 8,99 . Abholung in den Filialen möglich. Expressversand möglich.")
    assert (chain.pickup, chain.pickup_note) == (True, "a bolt üzleteiben")
    assert from_german_text("Sofort verfügbar Keine Abholung möglich.").pickup is False
    assert from_german_text("Lieferzeit 1-2 Werktage").pickup is None  # silence is not a "no" elsewhere
    store = from_german_text("Kreditkarte/Bankomat bei Abholung möglich. Preis bei Kauf & Mitnahme im Store",
                             "BahnhofCity Wien West: nicht lagernd Citygate Wien: nicht lagernd")
    assert (store.home, store.pickup, store.pickup_note) == (False, True, "BahnhofCity Wien West")
    assert store.lines_hu()[0] == "csak üzletben vehető át"


def test_carrier_badges_and_hungarian_text():
    assert from_carriers(["DHL", "Spedition", "Deutsche Post", "PickPoint"]).lines_hu()[2] == "csomagpont: igen (PickPoint)"
    possible = from_carriers(["DHL", "UPS", "Spedition"])
    assert (possible.home, possible.parcel, possible.parcel_note) == (True, "possible", "DHL, UPS")
    assert from_carriers([]).known() is False
    ipon = from_hungarian_text("Ingyenes szállítás , 4 nap alatt Személyes átvét, Futár, PickPack, Foxpost Kártya, Utalás")
    assert ipon.lines_hu() == ["házhozszállítás: igen", "személyes átvétel: igen", "csomagpont: igen (Foxpost, PickPack)"]


def test_merge_prefers_stated_facts():
    idealo = Delivery(home=True, parcel="possible", parcel_note="DHL, DPD")
    geizhals = Delivery(home=True, pickup=True, pickup_note="D-09603 Siebenlehn")
    billiger = Delivery(home=True, pickup=False)
    merged = billiger.merge(idealo).merge(geizhals)
    assert merged.lines_hu() == ["házhozszállítás: igen", "személyes átvétel: igen (D-09603 Siebenlehn)",
                                 "csomagpont: lehetséges (DHL, DPD)"]
    assert Delivery().lines_hu() == ["házhozszállítás: nincs adat", "személyes átvétel: nincs adat", "csomagpont: nincs adat"]


def offer(source, country, merchant, price, delivery=None, variant="Platin"):
    return Offer(source, country, merchant, "Surface Pro 11", price, "EUR", "https://x.example",
                 variant=variant, delivery=delivery or Delivery())


def test_dedupe_pools_delivery_per_merchant_and_country_and_adds_curated_facts():
    cfg = load_config(ROOT / "config" / "config.yaml")
    offers = [
        offer("idealo_de", "DE", "cyberport.de", 1660.39, Delivery(home=True, parcel="possible", parcel_note="DHL, DPD")),
        offer("heise", "DE", "Cyberport.de", 1665.00, Delivery(home=True, pickup=True, pickup_note="D-09603 Siebenlehn")),
        offer("idealo_at", "AT", "cyberport.at", 1674.34, Delivery(home=True, parcel="possible", parcel_note="DHL, DPD")),
        offer("idealo_at", "AT", "galaxus.at", 1684.33, Delivery(home=True, parcel="possible", parcel_note="DHL")),
        offer("geizhals_at", "AT", "Cyberport Stores Österreich", 1684.0,
              Delivery(home=False, pickup=True, pickup_note="BahnhofCity Wien West")),
        offer("shops_ch", "CH", "BRACK.CH", 1624.0),
    ]
    by = {(o.country, o.merchant): o for o in dedupe(offers, cfg.merchant_delivery)}
    de = by[("DE", "cyberport.de")]
    assert de.price == 1660.39 and de.delivery.pickup_note == "D-09603 Siebenlehn" and de.delivery.parcel == "possible"
    at = by[("AT", "cyberport.at")]  # German pickup address must not leak into the Austrian offer
    assert at.delivery.pickup is True and "Wien" in at.delivery.pickup_note
    assert by[("AT", "galaxus.at")].delivery.pickup is False
    brack = by[("CH", "BRACK.CH")].delivery
    assert brack.lines_hu() == ["házhozszállítás: igen", "személyes átvétel: igen (Mägenwil, Willisau)",
                                "csomagpont: igen (PickMup (Migros), PickPost, My Post 24)"]


def test_adapters_fill_delivery_from_real_rows():
    cfg = load_config(ROOT / "config" / "config.yaml")
    ctx = SourceContext(HttpClient(min_delay=0), Matcher(cfg.must_match, cfg.must_not_match, cfg.mpns))
    adapters = load_adapters()
    read = lambda name: (FIXTURES / name).read_text(encoding="utf-8")
    heise = adapters["geizhals"]("heise", {}, ctx).parse(read("heise_offers.html"), {"url": "u"}, {"AT", "DE"})
    easy, galaxus, etec = heise
    assert (easy.delivery.pickup, easy.delivery.pickup_note) == (True, "D-76287 Rheinstetten")
    assert galaxus.delivery.pickup is False and galaxus.delivery.note == "csak Németországon belül szállít"
    assert (etec.delivery.pickup, etec.delivery.pickup_note) == (True, "a bolt üzleteiben")
    idealo = adapters["idealo"]("idealo_at", {}, ctx).parse(read("idealo_offers.html"), {"url": "u", "country": "AT"})
    assert idealo[0].delivery.parcel == "possible" and "Österreichische Post" in idealo[0].delivery.parcel_note
    ipon = adapters["olcsobbat"]("olcsobbat", {}, ctx).parse(read("olcsobbat_offers.html"), {"url": "u"})[0]
    assert ipon.delivery.pickup is True and ipon.delivery.parcel == "yes"


def test_existing_database_gets_the_delivery_column(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "pricewatch.sqlite3")
    db.execute("CREATE TABLE offers (run_id INTEGER, run_date TEXT, source TEXT, country TEXT, merchant TEXT,"
               " merchant_key TEXT, title TEXT, variant TEXT, price REAL, currency TEXT, price_eur REAL,"
               " shipping REAL, availability TEXT, url TEXT)")
    db.commit()
    db.close()
    storage = Storage(tmp_path)
    assert "delivery" in {row["name"] for row in storage.db.execute("PRAGMA table_info(offers)")}
    storage.close()
