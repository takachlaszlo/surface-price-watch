"""SQLite price history."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .models import Offer, SourceResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    offers INTEGER DEFAULT 0,
    mailed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS offers (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    run_date TEXT NOT NULL,
    source TEXT NOT NULL,
    country TEXT NOT NULL,
    merchant TEXT NOT NULL,
    merchant_key TEXT NOT NULL,
    title TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    price_eur REAL,
    shipping REAL,
    availability TEXT,
    url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_offers_run ON offers(run_id);
CREATE INDEX IF NOT EXISTS idx_offers_country_date ON offers(country, run_date);
CREATE TABLE IF NOT EXISTS source_status (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    offers INTEGER NOT NULL,
    message TEXT,
    duration REAL
);
CREATE TABLE IF NOT EXISTS fx (
    rate_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (rate_date, currency)
);
"""


class Storage:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "pricewatch.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # -- runs ---------------------------------------------------------------
    def start_run(self, now: datetime) -> int:
        cur = self.db.execute(
            "INSERT INTO runs (run_date, started_at) VALUES (?, ?)",
            (now.date().isoformat(), now.isoformat(timespec="seconds")),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, now: datetime, offers: list[Offer], sources: list[SourceResult]) -> None:
        run_date = self.db.execute("SELECT run_date FROM runs WHERE id = ?", (run_id,)).fetchone()["run_date"]
        self.db.executemany(
            "INSERT INTO offers (run_id, run_date, source, country, merchant, merchant_key, title, variant,"
            " price, currency, price_eur, shipping, availability, url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (run_id, run_date, o.source, o.country, o.merchant, o.merchant_key, o.title, o.variant,
                 o.price, o.currency, o.price_eur, o.shipping, o.availability, o.url)
                for o in offers
            ],
        )
        self.db.executemany(
            "INSERT INTO source_status (run_id, source, status, offers, message, duration) VALUES (?,?,?,?,?,?)",
            [(run_id, s.source_id, s.status, s.offers, s.message, s.duration) for s in sources],
        )
        self.db.execute(
            "UPDATE runs SET finished_at = ?, offers = ? WHERE id = ?",
            (now.isoformat(timespec="seconds"), len(offers), run_id),
        )
        self.db.commit()

    def mark_mailed(self, run_id: int) -> None:
        self.db.execute("UPDATE runs SET mailed = 1 WHERE id = ?", (run_id,))
        self.db.commit()

    def has_completed_run_on(self, run_date: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM runs WHERE run_date = ? AND finished_at IS NOT NULL AND mailed = 1 LIMIT 1", (run_date,)
        ).fetchone()
        return row is not None

    # -- history ------------------------------------------------------------
    def previous_run_id(self, run_id: int) -> int | None:
        """Latest finished run from an earlier calendar day (so reruns compare to yesterday)."""
        row = self.db.execute(
            "SELECT id FROM runs WHERE finished_at IS NOT NULL AND offers > 0 AND id < ?"
            " AND run_date < (SELECT run_date FROM runs WHERE id = ?) ORDER BY id DESC LIMIT 1",
            (run_id, run_id),
        ).fetchone()
        return int(row["id"]) if row else None

    def merchant_prices(self, run_id: int) -> dict[tuple[str, str, str], float]:
        """(country, merchant_key, variant) -> price for one run."""
        rows = self.db.execute(
            "SELECT country, merchant_key, lower(variant) AS variant, MIN(price) AS price FROM offers"
            " WHERE run_id = ? GROUP BY country, merchant_key, lower(variant)",
            (run_id,),
        ).fetchall()
        return {(r["country"], r["merchant_key"], r["variant"]): r["price"] for r in rows}

    def country_min(self, run_id: int) -> dict[str, float]:
        rows = self.db.execute(
            "SELECT country, MIN(price) AS price FROM offers WHERE run_id = ? GROUP BY country", (run_id,)
        ).fetchall()
        return {r["country"]: r["price"] for r in rows}

    def daily_minimums(self, country: str, days: int) -> list[tuple[str, float]]:
        """Lowest price per calendar day (oldest first) for the last `days` days with data."""
        with closing(self.db.execute(
            "SELECT run_date, MIN(price) AS price FROM offers WHERE country = ?"
            " GROUP BY run_date ORDER BY run_date DESC LIMIT ?",
            (country, days),
        )) as cur:
            rows = cur.fetchall()
        return [(r["run_date"], r["price"]) for r in reversed(rows)]

    def all_time_low(self, country: str) -> tuple[float, str, str] | None:
        row = self.db.execute(
            "SELECT price, run_date, merchant FROM offers WHERE country = ? ORDER BY price ASC, run_date ASC LIMIT 1",
            (country,),
        ).fetchone()
        return (row["price"], row["run_date"], row["merchant"]) if row else None

    # -- fx -----------------------------------------------------------------
    def save_fx(self, rate_date: str, rates: dict[str, float]) -> None:
        self.db.executemany(
            "INSERT OR REPLACE INTO fx (rate_date, currency, rate) VALUES (?,?,?)",
            [(rate_date, cur, rate) for cur, rate in rates.items()],
        )
        self.db.commit()

    def latest_fx(self) -> tuple[str, dict[str, float]] | None:
        row = self.db.execute("SELECT MAX(rate_date) AS d FROM fx").fetchone()
        if not row or not row["d"]:
            return None
        rows = self.db.execute("SELECT currency, rate FROM fx WHERE rate_date = ?", (row["d"],)).fetchall()
        return row["d"], {r["currency"]: r["rate"] for r in rows}
