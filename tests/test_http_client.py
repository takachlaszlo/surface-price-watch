"""HttpClient behaviour with a fake `requests` session – no network involved."""
import pytest

from pricewatch.http import BlockedError, FetchError, HttpClient, RobotsDisallowed


class FakeResponse:
    def __init__(self, status, body=b"<html>ok</html>", headers=None, url="https://x.test/p"):
        self.status_code, self.content, self.url = status, body, url
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        result = self.routes[url]
        if isinstance(result, Exception):
            raise result
        return result


def client(routes, **kw):
    c = HttpClient(min_delay=0, retries=1, **kw)
    c.session = FakeSession(routes)
    return c


def test_robots_disallow_blocks_fetch_and_allowed_path_passes():
    c = client({
        "https://x.test/robots.txt": FakeResponse(200, b"User-agent: *\nDisallow: /?fs=\n"),
        "https://x.test/product-a1.html?hloc=at": FakeResponse(200, b"<html>product</html>"),
    })
    assert c.get_text("https://x.test/product-a1.html?hloc=at") == "<html>product</html>"
    with pytest.raises(RobotsDisallowed):
        c.get("https://x.test/?fs=surface")
    assert c.session.calls.count("https://x.test/robots.txt") == 1  # cached per origin


def test_403_and_challenge_page_are_blocked_not_retried():
    c = client({
        "https://x.test/robots.txt": FakeResponse(404),
        "https://x.test/a": FakeResponse(403),
        "https://x.test/b": FakeResponse(200, b"<html><title>Just a moment...</title></html>"),
    })
    with pytest.raises(BlockedError):
        c.get("https://x.test/a")
    with pytest.raises(BlockedError):
        c.get("https://x.test/b")
    assert c.session.calls.count("https://x.test/a") == 1


def test_5xx_is_retried_then_fails():
    c = client({"https://x.test/robots.txt": FakeResponse(404), "https://x.test/a": FakeResponse(503)})
    with pytest.raises(FetchError):
        c.get("https://x.test/a")
    assert c.session.calls.count("https://x.test/a") == 2


def test_charset_from_header_wins_over_utf8_guess():
    latin = "Preis: 1.599,00 € – Zubehör".encode("cp1252")
    c = client({
        "https://x.test/robots.txt": FakeResponse(404),
        "https://x.test/a": FakeResponse(200, latin, {"Content-Type": "text/html; charset=windows-1252"}),
        "https://x.test/b": FakeResponse(200, "Ár: 459 990 Ft".encode("utf-8"), {"Content-Type": "text/html"}),
    })
    assert c.get_text("https://x.test/a") == "Preis: 1.599,00 € – Zubehör"
    assert c.get_text("https://x.test/b") == "Ár: 459 990 Ft"


def test_json_helper():
    c = client({"https://x.test/robots.txt": FakeResponse(404),
                "https://x.test/api": FakeResponse(200, b'{"price": 1}', {"Content-Type": "application/json"})})
    assert c.get_json("https://x.test/api") == {"price": 1}
