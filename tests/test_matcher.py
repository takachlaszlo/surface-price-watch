from pricewatch.matcher import Matcher

MUST = [r"surface\s*pro", r"\b11\b|11th|11\.", r"ultra\s*5|236V|238V", r"16\s*GB", r"256\s*GB"]
MUST_NOT = [r"snapdragon|x\s*plus|x\s*elite", r"ultra\s*7", r"\b(8|32)\s*GB\b", r"512\s*GB|1\s*TB",
            r"pro\s*10\b", r"refurb|gebraucht|használt|b-ware"]


def make():
    return Matcher(MUST, MUST_NOT, ["EP2-00004", "EP2-00012"])


def test_accepts_full_title():
    assert make().matches("Microsoft Surface Pro 11 Intel Core Ultra 5 236V 16GB 256GB Platin, W11 Pro")


def test_rejects_wrong_cpu_or_size():
    m = make()
    assert not m.matches("Microsoft Surface Pro 11 Snapdragon X Plus 16GB 256GB")
    assert not m.matches("Surface Pro 11 Ultra 7 268V 16GB 256GB")
    assert not m.matches("Surface Pro 11 Ultra 5 236V 16GB 512GB")
    assert not m.matches("Surface Pro 10 Ultra 5 135U 16GB 256GB")


def test_mpn_wins_over_terse_title_but_not_over_exclusions():
    m = make()
    assert m.matches("Surface Pro 11 for Business", mpn="EP2-00004")
    assert m.matches("Tablet EP2-00012 Platin")
    assert not m.matches("Surface Pro 11 EP2-00004 refurbished")


def test_variant_label():
    assert Matcher.variant_label("Surface Pro 11 Ultra 5 Platin OLED 5G") == "Platin, OLED, 5G"
    assert Matcher.variant_label("Surface Pro 11 schwarz") == "Fekete"
    assert Matcher.variant_label("Surface Pro 11 16/256") == ""
