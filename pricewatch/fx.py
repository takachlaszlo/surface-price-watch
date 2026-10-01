"""EUR reference rates from the European Central Bank (for cross-country comparison only)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from .http import FetchError, HttpClient
from .storage import Storage

log = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def load_rates(http: HttpClient, storage: Storage, fallback: dict[str, float]) -> tuple[dict[str, float], str]:
    """Return ({currency: units per 1 EUR}, human note about where the rates came from)."""
    try:
        root = ET.fromstring(http.get(ECB_URL).content)
        rate_date, rates = "", {"EUR": 1.0}
        for node in root.iter():
            if node.tag.endswith("Cube"):
                if "time" in node.attrib:
                    rate_date = node.attrib["time"]
                if "currency" in node.attrib:
                    rates[node.attrib["currency"]] = float(node.attrib["rate"])
        if "CHF" in rates and "HUF" in rates and rate_date:
            storage.save_fx(rate_date, rates)
            return rates, f"EKB referencia-árfolyam, {rate_date}"
        raise FetchError("hiányos EKB válasz")
    except (FetchError, ET.ParseError, ValueError) as exc:
        log.warning("ECB rates unavailable: %s", exc)
    cached = storage.latest_fx()
    if cached:
        return cached[1], f"utolsó mentett EKB árfolyam, {cached[0]}"
    rates = {"EUR": 1.0, **fallback}
    return rates, "beállított tartalék árfolyam (az EKB nem volt elérhető)"


def to_eur(amount: float, currency: str, rates: dict[str, float]) -> float | None:
    rate = rates.get(currency.upper())
    return round(amount / rate, 2) if rate else None
