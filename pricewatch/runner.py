"""One monitoring run: query every source, clean up the offers, store and report."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from . import fx
from .config import Config
from .http import BlockedError, FetchError, HttpClient, RobotsDisallowed
from .mailer import send_with_retry
from .delivery import Delivery
from .matcher import Matcher
from .models import COUNTRIES, Offer, RunResult, SourceResult
from .report import build_report
from .sources import SourceContext, load_adapters
from .storage import Storage

log = logging.getLogger(__name__)


def collect(cfg: Config, http: HttpClient, only: set[str] | None = None) -> tuple[list[Offer], list[SourceResult]]:
    adapters = load_adapters()
    ctx = SourceContext(http=http, matcher=Matcher(cfg.must_match, cfg.must_not_match, cfg.mpns))
    offers: list[Offer] = []
    results: list[SourceResult] = []
    for src in cfg.sources:
        if not src.enabled or (only and src.id not in only):
            continue
        started = time.monotonic()
        result = SourceResult(source_id=src.id, status="ok")
        try:
            adapter = adapters.get(src.adapter)
            if adapter is None:
                raise FetchError(f"ismeretlen adapter: {src.adapter}")
            found = adapter(src.id, src.options, ctx).fetch()
            kept, dropped = _validate(found, cfg)
            offers.extend(kept)
            result.offers = len(kept)
            if dropped:
                result.message = f"{dropped} ajánlat kiszűrve (ár/ország ellenőrzés)"
            if not kept:
                result.status = "empty"
        except BlockedError as exc:
            result.status, result.message = "blocked", str(exc)
        except RobotsDisallowed as exc:
            result.status, result.message = "robots", str(exc)
        except FetchError as exc:
            result.status, result.message = "error", str(exc)
        except Exception as exc:  # a parser bug in one adapter must not stop the run
            log.exception("source %s crashed", src.id)
            result.status, result.message = "error", f"{type(exc).__name__}: {exc}"
        result.duration = round(time.monotonic() - started, 1)
        log.info("%-24s %-8s %3d ajánlat  %s", src.id, result.status, result.offers, result.message)
        results.append(result)
    return offers, results


def _validate(found: list[Offer], cfg: Config) -> tuple[list[Offer], int]:
    kept: list[Offer] = []
    for offer in found:
        low, high = cfg.price_limits.get(offer.currency, (0.0, float("inf")))
        if (
            offer.country in COUNTRIES
            and offer.country in cfg.countries
            and offer.url
            and offer.merchant
            and low <= offer.price <= high
        ):
            kept.append(offer)
        else:
            log.debug("dropped offer: %s", offer)
    return kept, len(found) - len(kept)


def dedupe(offers: list[Offer], known: dict[tuple[str, str], Delivery] | None = None) -> list[Offer]:
    """The same merchant shows up through several comparison sites: keep its best price,
    and pool what the sites (and the curated `merchant_delivery` list) say about delivery."""
    best: dict[tuple[str, str, str], Offer] = {}
    delivery: dict[tuple[str, str], Delivery] = {}
    for offer in offers:
        merchant = (offer.country, offer.merchant_key)
        delivery[merchant] = delivery[merchant].merge(offer.delivery) if merchant in delivery else offer.delivery
        current = best.get(offer.dedup_key)
        if current is None or offer.price < current.price:
            best[offer.dedup_key] = offer
    for (country, key), info in list(delivery.items()):
        base = (country, key.split("stores")[0])
        if "stores" in key and info.pickup and base in delivery:  # "Cyberport Stores Österreich" -> Cyberport
            delivery[base] = delivery[base].merge(Delivery(pickup=True, pickup_note=info.pickup_note))
    for offer in best.values():
        merchant = (offer.country, offer.merchant_key)
        offer.delivery = delivery[merchant]
        if known and merchant in known:
            offer.delivery = offer.delivery.merge(known[merchant])
    return list(best.values())


def run_once(cfg: Config, *, send_mail: bool = True, only: set[str] | None = None) -> RunResult:
    storage = Storage(cfg.data_dir)
    try:
        http = HttpClient(cfg.user_agent, cfg.min_delay, cfg.timeout, cfg.respect_robots)
        now = datetime.now()
        run_id = storage.start_run(now)
        log.info("futás #%d indul – %d forrás", run_id, sum(1 for s in cfg.sources if s.enabled))

        rates, fx_note = fx.load_rates(http, storage, cfg.fallback_fx)
        raw_offers, source_results = collect(cfg, http, only)
        for offer in raw_offers:
            offer.price_eur = fx.to_eur(offer.price, offer.currency, rates)
        offers = dedupe(raw_offers, cfg.merchant_delivery)
        storage.finish_run(run_id, datetime.now(), offers, source_results)

        result = RunResult(run_id=run_id, run_date=now.date().isoformat(), offers=offers,
                           sources=source_results, fx=rates, fx_note=fx_note)
        subject, html, text = build_report(result, cfg, storage)
        (cfg.data_dir / "last_report.html").write_text(html, encoding="utf-8")
        (cfg.data_dir / "last_report.txt").write_text(text, encoding="utf-8")
        log.info("futás #%d kész: %d ajánlat, %d HTTP kérés", run_id, len(offers), http.request_count)

        if send_mail:
            send_with_retry(cfg.mail, subject, html, text)
            storage.mark_mailed(run_id)
            log.info("jelentés elküldve: %s", ", ".join(cfg.mail.recipients))
        return result
    finally:
        storage.close()
