"""How an offer can reach the buyer: home delivery, pickup in a shop, parcel points.

Every field is three-valued – the comparison sites say a lot, but not
everything, and "not stated" must never be shown as "no".
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

# what a carrier badge tells about parcel points: the carrier's own pickup network
_CARRIER_NETWORKS = {
    "dhl": "DHL",
    "deutsche post": "Deutsche Post",
    "österreichische post": "Österreichische Post",
    "hermes": "Hermes",
    "dpd": "DPD",
    "gls": "GLS",
    "ups": "UPS",
}
_PARCEL_RANK = {"": 0, "no": 1, "possible": 2, "yes": 3}


@dataclass
class Delivery:
    home: bool | None = None      # delivers to the door
    pickup: bool | None = None    # can be collected in the merchant's own shop
    pickup_note: str = ""         # where
    parcel: str = ""              # "" unknown | "no" | "possible" (carrier has points) | "yes" (stated)
    parcel_note: str = ""         # which networks
    note: str = ""                # e.g. "csak Ausztrián belül szállít"

    def merge(self, other: "Delivery") -> "Delivery":
        """Combine what two sources say about the same merchant; a stated fact beats silence,
        a stated possibility beats a stated "no" (the more detailed listing knows better)."""
        pickup, pickup_note = self.pickup, self.pickup_note
        if other.pickup and not (self.pickup and self.pickup_note):
            pickup, pickup_note = True, other.pickup_note or self.pickup_note
        elif pickup is None:
            pickup = other.pickup
        mine, theirs = _PARCEL_RANK[self.parcel], _PARCEL_RANK[other.parcel]
        if theirs > mine:
            parcel, parcel_note = other.parcel, other.parcel_note
        else:
            parcel, parcel_note = self.parcel, self.parcel_note
            if theirs == mine and other.parcel_note and other.parcel_note not in parcel_note:
                parcel_note = ", ".join(x for x in (parcel_note, other.parcel_note) if x)
        return Delivery(
            home=self.home if self.home is not None else other.home,
            pickup=pickup,
            pickup_note=pickup_note,
            parcel=parcel,
            parcel_note=parcel_note,
            note=self.note or other.note,
        )

    def known(self) -> bool:
        return self.home is not None or self.pickup is not None or bool(self.parcel) or bool(self.note)

    def lines_hu(self) -> list[str]:
        """Short Hungarian phrases for the report, in a fixed order."""
        if self.home is False and self.pickup:
            first = "csak üzletben vehető át"
        elif self.home:
            first = "házhozszállítás: igen"
        else:
            first = "házhozszállítás: nincs adat"
        if self.pickup:
            second = "személyes átvétel: igen" + (f" ({self.pickup_note})" if self.pickup_note else "")
        elif self.pickup is False:
            second = "személyes átvétel: nincs"
        else:
            second = "személyes átvétel: nincs adat"
        if self.parcel == "yes":
            third = "csomagpont: igen" + (f" ({self.parcel_note})" if self.parcel_note else "")
        elif self.parcel == "possible":
            third = f"csomagpont: lehetséges ({self.parcel_note})"
        elif self.parcel == "no":
            third = "csomagpont: nincs"
        else:
            third = "csomagpont: nincs adat"
        return [first, second, third] + ([self.note] if self.note else [])

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Delivery":
        data = data or {}
        parcel = data.get("parcel", data.get("parcel_point", ""))
        if isinstance(parcel, bool):
            parcel = "yes" if parcel else "no"
        return cls(
            home=data.get("home"),
            pickup=data.get("pickup"),
            pickup_note=str(data.get("pickup_note") or ""),
            parcel=str(parcel or ""),
            parcel_note=str(data.get("parcel_note") or ""),
            note=str(data.get("note") or ""),
        )


def from_carriers(badges: list[str]) -> Delivery:
    """idealo-style carrier badges ("DHL", "Hermes", "PickPoint", "Spedition")."""
    names = [b.strip() for b in badges if b and b.strip()]
    if any(re.search(r"pick\s*point|abholstation|packstation|paketshop", n, re.I) for n in names):
        stated = [n for n in names if re.search(r"pick\s*point|abholstation|packstation|paketshop", n, re.I)]
        return Delivery(home=True, parcel="yes", parcel_note=", ".join(stated))
    networks = [_CARRIER_NETWORKS[n.lower()] for n in names if n.lower() in _CARRIER_NETWORKS]
    if networks:
        return Delivery(home=True, parcel="possible", parcel_note=", ".join(dict.fromkeys(networks)))
    return Delivery(home=True if names else None)


def from_german_text(text: str, store_stock: str = "", silence_means_no: bool = False) -> Delivery:
    """Geizhals / heise / billiger wording: "Abholung … möglich (D-35440 Linden)",
    "Keine Abholung möglich", "Lieferung nur innerhalb Österreichs", store price rows.

    Geizhals prints the pickup line for every merchant that offers it, so there
    (`silence_means_no`) a filled-in delivery text without it means "no pickup"."""
    info = Delivery(home=True)
    if re.search(r"Preis bei Kauf & Mitnahme im Store", text):
        stores = re.match(r"\s*([^:]{3,160}):", store_stock or "")
        return Delivery(home=False, pickup=True, pickup_note=stores.group(1).strip() if stores else "üzletekben")
    if re.search(r"keine\s+Abholung", text, re.I):
        info.pickup = False
    else:
        pickup = re.search(r"Abholung\b[^.()]*?möglich\s*(?:\(([^)]*)\))?", text, re.I)
        if pickup:
            info.pickup = True
            where = (pickup.group(1) or "").strip()
            if not where and re.search(r"Filiale", pickup.group(0), re.I):
                where = "a bolt üzleteiben"
            info.pickup_note = where
        elif silence_means_no and text.strip():
            info.pickup = False
    only = re.search(r"Lieferung nur innerhalb (Deutschlands|Österreichs|der Schweiz)", text)
    if only:
        country = {"Deutschlands": "Németországon", "Österreichs": "Ausztrián", "der Schweiz": "Svájcon"}[only.group(1)]
        info.note = f"csak {country} belül szállít"
    return info


def from_hungarian_text(text: str) -> Delivery:
    """olcsobbat.hu wording: "Személyes átvét, Futár, PickPack, Foxpost"."""
    info = Delivery()
    if re.search(r"\bFutár\b|házhoz", text, re.I):
        info.home = True
    if re.search(r"Személyes átv", text, re.I):
        info.pickup = True
    points = [name for name, rx in (
        ("Foxpost", r"foxpost"), ("PickPack", r"pick\s*pack"), ("GLS csomagpont", r"gls\s*(csomagpont|pont|automata)"),
        ("Packeta", r"packeta"), ("MPL / posta", r"\bmpl\b|postán maradó|postapont"), ("easybox", r"easybox"),
        ("csomagautomata", r"csomagautomata"),
    ) if re.search(rx, text, re.I)]
    if points:
        info.parcel, info.parcel_note = "yes", ", ".join(points)
    return info
