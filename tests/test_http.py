from pricewatch.http import RobotsRules

GEIZHALS = """
User-agent: *
Disallow: /redir/
Disallow: /?fs=
Disallow: /*?*sort=
Disallow: /hardware/

User-agent: ClaudeBot
Disallow: /redir/
"""


def test_wildcard_and_group_selection():
    rules = RobotsRules(GEIZHALS, "Mozilla/5.0 (compatible; SurfacePriceWatch/1.0)")
    assert rules.allowed("/microsoft-surface-pro-11-a123.html")
    assert rules.allowed("/microsoft-surface-pro-11-a123.html?hloc=at&hloc=de")
    assert not rules.allowed("/?fs=surface")
    assert not rules.allowed("/a123.html?hloc=at&sort=p")
    assert not rules.allowed("/hardware/")
    assert not rules.allowed("/redir/123")


def test_specific_agent_group_wins():
    rules = RobotsRules(GEIZHALS, "ClaudeBot/1.0")
    assert rules.allowed("/?fs=surface")
    assert not rules.allowed("/redir/1")


def test_allow_overrides_shorter_disallow_and_dollar_anchor():
    rules = RobotsRules("User-agent: *\nDisallow: /p/\nAllow: /p/public\nDisallow: /*.pdf$\n", "x")
    assert rules.allowed("/p/public/1")
    assert not rules.allowed("/p/private")
    assert not rules.allowed("/doc.pdf")
    assert rules.allowed("/doc.pdf?x=1")


def test_empty_robots_allows_all():
    assert RobotsRules("", "x").allowed("/anything")
