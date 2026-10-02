from pricewatch.delivery import Delivery
from pricewatch.financing import Financing, for_price, from_page
from pricewatch.models import Offer
from pricewatch.runner import dedupe

NOTEBOOK_HU = """
<html><body>
<div class="loan-box"><div class="d-flex loan"><div class="loan-text"><div class="title">Otp Online áruhitel</div>
 <div class="desc"><span class="loan-details loan-details-color">22 399 FT x 48 HÓ</span>
 <span class="loan-details"><span style="font-weight: 700;">THM: 19.9%</span> | Önrész: 0 FT</span></div></div></div></div>
<div class="loan-box instacash-calc"><div class="d-flex"><div class="loan-text"><div class="title">Bankmentes részletfizetés</div>
 <div class="desc"><span class="loan-details bigger">151 580 FT x 4 HÓ</span>
 <span class="loan-details"><span style="font-weight: 700;">THM: 0%</span> | Önerő: 151 580 FT</span></div></div></div></div>
<a title="iPhone részletre, akár 0% THM online áruhitel">blog</a>
</body></html>
"""


def test_product_page_with_a_zero_percent_plan():
    info = from_page(NOTEBOOK_HU)
    assert info.thm0 == "yes"
    assert info.terms == "4 × 151 580 Ft + 151 580 Ft önerő (Bankmentes részletfizetés)"
    assert info.other == "Otp Online áruhitel 48 hó, THM 19,9%"
    assert info.line_hu().startswith("0% THM: igen – 4 × 151 580 Ft")


def test_only_interest_bearing_plans_and_no_plans():
    paid_only = NOTEBOOK_HU.split('<div class="loan-box instacash-calc">')[0] + "</body></html>"
    info = from_page(paid_only)
    assert (info.thm0, info.other) == ("no", "Otp Online áruhitel 48 hó, THM 19,9%")
    # a site-wide "akár 0% THM" banner is not a statement about this product
    banner = '<html><body><a title="akár 0% THM online áruhitel">Hitel</a><p>Hitelkalkulátor THM: %</p></body></html>'
    assert from_page(banner) == Financing() and from_page(banner).line_hu() == "0% THM: nincs adat"


def test_shop_rule_applied_to_the_price():
    milpay = {"thm0": "yes", "terms": "MilPay", "instalments": 4, "min_price": 100000, "max_price": 1000000}
    inside = for_price(milpay, 743190)
    assert (inside.thm0, inside.terms) == ("yes", "4 × 185 798 Ft – MilPay")
    outside = for_price(milpay, 1200000)
    assert outside.thm0 == "no" and "100 000 Ft – 1 000 000 Ft" in outside.terms
    assert for_price({"thm0": "possible", "terms": "megjelölt termékekre"}, 795116).line_hu() == \
        "0% THM: lehetséges – megjelölt termékekre"


def offer(source, merchant, price, financing=None):
    return Offer(source, "HU", merchant, "Surface Pro 11", price, "HUF", "https://x.example",
                 variant="Platin", delivery=Delivery(), financing=financing or Financing())


def test_page_statement_beats_shop_rule_and_survives_dedupe():
    rules = {("HU", "notebook"): {"thm0": "possible", "terms": "nem minden termékre"},
             ("HU", "ipon"): {"thm0": "yes", "terms": "MilPay", "instalments": 4, "min_price": 100000, "max_price": 1000000},
             ("HU", "bluechip"): {"thm0": "no", "terms": "THM 19,90%"}}
    offers = [
        offer("shops_hu", "notebook.hu", 757900, from_page(NOTEBOOK_HU)),
        offer("olcsobbat", "notebook.hu", 757000),            # cheaper listing without loan details
        offer("olcsobbat", "iPon", 743190),
        offer("shops_hu", "Bluechip", 747900),
        offer("shops_hu", "eMAG", 795116),                     # no rule, no page data
    ]
    by = {o.merchant: o for o in dedupe(offers, None, rules)}
    assert by["notebook.hu"].price == 757000 and by["notebook.hu"].financing.thm0 == "yes"
    assert by["notebook.hu"].financing.terms.startswith("4 × 151 580 Ft")
    assert by["iPon"].financing.terms == "4 × 185 798 Ft – MilPay"
    assert by["Bluechip"].financing.line_hu() == "0% THM: nincs – THM 19,90%"
    assert by["eMAG"].financing.line_hu() == "0% THM: nincs adat"
