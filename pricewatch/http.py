"""A deliberately plain, polite HTTP client.

The monitor identifies itself honestly, waits between requests to the same
host, honours robots.txt and never tries to get around bot protection: when a
site answers with a block or a challenge page the source is reported as
"blocked" and skipped.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; SurfacePriceWatch/1.0; personal daily price monitor)"

_CHALLENGE_MARKERS = re.compile(
    r"just a moment|nur einen moment|cf-chl|challenge-platform|captcha|access denied|"
    r"pardon our interruption|are you a robot|bot detection|request unsuccessful|px-captcha",
    re.IGNORECASE,
)
_BLOCK_STATUSES = {401, 403, 429, 451}


class FetchError(Exception):
    """The request failed for a technical reason (network, 5xx, bad payload)."""


class BlockedError(FetchError):
    """The site refused the automated client; we do not work around that."""


class RobotsDisallowed(FetchError):
    """robots.txt does not allow this URL for our user agent."""


class RobotsRules:
    """Minimal robots.txt matcher with '*' and '$' support (longest rule wins)."""

    def __init__(self, text: str, agent_token: str):
        self.rules: list[tuple[bool, re.Pattern[str], int]] = []
        groups: dict[str, list[tuple[bool, str]]] = {}
        agents: list[str] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:
                    agents, in_rules = [], False
                agents.append(value.lower())
                groups.setdefault(value.lower(), [])
            elif key in ("allow", "disallow"):
                in_rules = True
                for agent in agents:
                    groups[agent].append((key == "allow", value))
        token = agent_token.lower()
        chosen = next((rules for agent, rules in groups.items() if agent != "*" and agent in token), None)
        if chosen is None:
            chosen = groups.get("*", [])
        for allow, path in chosen:
            if not path:
                continue  # "Disallow:" with empty value allows everything
            pattern = re.escape(path).replace(r"\*", ".*")
            if pattern.endswith(r"\$"):
                pattern = pattern[:-2] + "$"
            self.rules.append((allow, re.compile(pattern), len(path)))

    def allowed(self, path: str) -> bool:
        best_len, best_allow = -1, True
        for allow, pattern, length in self.rules:
            if pattern.match(path) and (length > best_len or (length == best_len and allow)):
                best_len, best_allow = length, allow
        return best_allow


@dataclass
class Response:
    """What adapters see: bytes, headers and a charset-aware `.text`."""
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    encoding: str | None = None

    @property
    def text(self) -> str:
        for enc in (self.encoding, "utf-8", "cp1252"):
            if enc:
                try:
                    return self.content.decode(enc)
                except UnicodeDecodeError:
                    continue
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        import json
        return json.loads(self.text)


class HttpClient:
    """One plain `requests` session that is honest about who it is.

    A 403 / 429 or a challenge page means the site does not want automated
    visitors: the source is reported as blocked, nothing is retried with a
    different disguise.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        min_delay: float = 3.0,
        timeout: float = 30.0,
        respect_robots: bool = True,
        retries: int = 2,
        accept_language: str = "de-CH,de;q=0.9,hu;q=0.8,en;q=0.7",
    ):
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.retries = retries
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": accept_language,
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotsRules | None] = {}
        self.request_count = 0

    # -- public API ---------------------------------------------------------
    def get(self, url: str, *, headers: dict | None = None) -> Response:
        self._check_robots(url)
        return self._request(url, headers=headers)

    def get_text(self, url: str, **kwargs) -> str:
        return self.get(url, **kwargs).text

    def get_json(self, url: str, **kwargs):
        response = self.get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise FetchError(f"nem JSON válasz: {url}") from exc

    # -- internals ----------------------------------------------------------
    def _throttle(self, host: str) -> None:
        wait = self._last_hit.get(host, 0.0) + self.min_delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _request(self, url: str, *, headers: dict | None = None) -> Response:
        host = urlsplit(url).netloc
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(host)
            self.request_count += 1
            try:
                r = self.session.get(url, headers=headers, timeout=self.timeout)
                response = Response(r.url, r.status_code, dict(r.headers), r.content, _charset(dict(r.headers)))
            except requests.RequestException as exc:
                last_error = exc
                log.debug("GET %s failed (%s), attempt %d", url, exc, attempt + 1)
                time.sleep(2 * (attempt + 1))
                continue
            status = response.status_code
            if status in _BLOCK_STATUSES:
                raise BlockedError(f"HTTP {status} – a webhely elutasítja az automatikus lekérdezést")
            if status >= 500:
                if _CHALLENGE_MARKERS.search(response.text[:20000]):
                    raise BlockedError(f"HTTP {status} – bot-ellenőrző oldal")
                last_error = FetchError(f"HTTP {status}")
                time.sleep(2 * (attempt + 1))
                continue
            if status >= 400:
                raise FetchError(f"HTTP {status}: {url}")
            if len(response.content) < 30000 and _CHALLENGE_MARKERS.search(response.text):
                raise BlockedError("bot-ellenőrző (challenge) oldal érkezett a tartalom helyett")
            return response
        raise FetchError(f"sikertelen lekérés: {url} ({last_error})")

    def _check_robots(self, url: str) -> None:
        if not self.respect_robots:
            return
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        rules = self._robots[origin]
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        if rules is not None and not rules.allowed(path):
            raise RobotsDisallowed(f"a robots.txt tiltja: {url}")

    def _load_robots(self, origin: str) -> RobotsRules | None:
        try:
            response = self._request(origin + "/robots.txt")
        except BlockedError:
            return None  # the page request itself will report the block
        except FetchError as exc:
            log.debug("robots.txt unreachable for %s: %s", origin, exc)
            return None  # no usable robots.txt -> no restrictions (RFC 9309)
        return RobotsRules(response.text, self.user_agent)


def _charset(headers: dict[str, str]) -> str | None:
    content_type = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
    match = re.search(r"charset=\"?([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else None
