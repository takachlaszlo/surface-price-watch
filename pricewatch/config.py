"""Configuration: config.yaml for what to watch, environment for how to deliver."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .delivery import Delivery
from .http import DEFAULT_USER_AGENT
from .models import normalize_merchant


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on", "igen")


@dataclass
class MailConfig:
    host: str
    port: int
    security: str  # none | starttls | ssl
    user: str
    password: str
    verify_tls: bool
    sender: str
    recipients: list[str]
    sender_name: str

    @classmethod
    def from_env(cls) -> "MailConfig":
        sender = _env("MAIL_FROM", "technikai@mail.home.arpa")
        recipients = [r.strip() for r in _env("MAIL_TO", sender).replace(";", ",").split(",") if r.strip()]
        return cls(
            host=_env("SMTP_HOST", "mail.home.arpa"),
            port=int(_env("SMTP_PORT", "25")),
            security=_env("SMTP_SECURITY", "none").lower(),
            user=_env("SMTP_USER"),
            password=_env("SMTP_PASSWORD"),
            verify_tls=_env_bool("SMTP_VERIFY_TLS", False),
            sender=sender,
            recipients=recipients,
            sender_name=_env("MAIL_FROM_NAME", "Surface árfigyelő"),
        )


@dataclass
class ScheduleConfig:
    run_at: str  # HH:MM local time
    run_on_start: bool
    catch_up: bool

    @classmethod
    def from_env(cls) -> "ScheduleConfig":
        return cls(
            run_at=_env("RUN_AT", "07:00"),
            run_on_start=_env_bool("RUN_ON_START", False),
            catch_up=_env_bool("CATCH_UP", True),
        )


@dataclass
class SourceConfig:
    id: str
    adapter: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    product_name: str
    must_match: list[str]
    must_not_match: list[str]
    mpns: list[str]
    price_limits: dict[str, tuple[float, float]]
    countries: list[str]
    top_n: int
    distinct_merchants: bool
    rank_by: str  # price | total
    fallback_fx: dict[str, float]
    user_agent: str
    min_delay: float
    timeout: float
    respect_robots: bool
    sources: list[SourceConfig]
    data_dir: Path
    mail: MailConfig
    schedule: ScheduleConfig
    # (country, merchant key) -> what is known about the shop's delivery options
    merchant_delivery: dict[tuple[str, str], Delivery] = field(default_factory=dict)


def _merchant_delivery(entries: list | None) -> dict[tuple[str, str], Delivery]:
    known: dict[tuple[str, str], Delivery] = {}
    for entry in entries or []:
        names = entry.get("merchants") or [entry["merchant"]]
        for name in names:
            known[(str(entry["country"]).upper(), normalize_merchant(str(name)))] = Delivery.from_dict(entry)
    return known


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg_path = Path(path or _env("PRICEWATCH_CONFIG", "/config/config.yaml"))
    with open(cfg_path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    product = raw.get("product", {})
    report = raw.get("report", {})
    http = raw.get("http", {})
    limits = {
        cur.upper(): (float(bounds[0]), float(bounds[1]))
        for cur, bounds in (product.get("price_limits") or {}).items()
    }
    sources = [
        SourceConfig(
            id=str(item["id"]),
            adapter=str(item["adapter"]),
            enabled=bool(item.get("enabled", True)),
            options=dict(item.get("options") or {}),
        )
        for item in raw.get("sources", [])
    ]
    seen: set[str] = set()
    for src in sources:
        if src.id in seen:
            raise ValueError(f"duplikált forrás-azonosító a config.yaml-ban: {src.id}")
        seen.add(src.id)

    return Config(
        product_name=product.get("name", "Microsoft Surface Pro 11"),
        must_match=list(product.get("must_match") or []),
        must_not_match=list(product.get("must_not_match") or []),
        mpns=[str(m) for m in (product.get("mpns") or [])],
        price_limits=limits,
        countries=[c.upper() for c in report.get("countries", ["CH", "HU", "AT", "DE"])],
        top_n=int(report.get("top_n", 3)),
        distinct_merchants=bool(report.get("distinct_merchants", True)),
        rank_by=str(report.get("rank_by", "price")),
        fallback_fx={k.upper(): float(v) for k, v in (raw.get("fallback_fx") or {}).items()},
        user_agent=str(http.get("user_agent") or DEFAULT_USER_AGENT),
        min_delay=float(http.get("min_delay_seconds", 3)),
        timeout=float(http.get("timeout_seconds", 30)),
        respect_robots=bool(http.get("respect_robots", True)),
        sources=sources,
        data_dir=Path(_env("PRICEWATCH_DATA", "/data")),
        mail=MailConfig.from_env(),
        schedule=ScheduleConfig.from_env(),
        merchant_delivery=_merchant_delivery(raw.get("merchant_delivery")),
    )
