"""Command line entry point: python -m pricewatch <command>."""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import load_config
from .http import HttpClient
from .mailer import send
from .report import fmt_money
from .runner import collect, run_once
from .scheduler import daemon
from .sources import load_adapters


def _setup_logging(cfg, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(cfg.data_dir / "pricewatch.log", maxBytes=1_000_000,
                                            backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="pricewatch", description="Surface Pro 11 árfigyelő")
    parser.add_argument("-c", "--config", help="config.yaml útvonala (alapértelmezés: /config/config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("daemon", help="folyamatos futás, napi ütemezéssel (a konténer alapparancsa)")
    run = sub.add_parser("run", help="egyszeri futás most")
    run.add_argument("--no-mail", action="store_true", help="ne küldjön levelet, csak mentse a jelentést")
    run.add_argument("--only", help="csak ezek a források (vesszővel elválasztott azonosítók)")
    check = sub.add_parser("check", help="egy forrás kipróbálása, az ajánlatok kiírása")
    check.add_argument("source_id")
    sub.add_parser("sources", help="a beállított források listája")
    sub.add_parser("test-mail", help="próbalevél küldése az SMTP-beállítások ellenőrzéséhez")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    _setup_logging(cfg, args.verbose)

    if args.command == "daemon":
        daemon(args.config)
    elif args.command == "run":
        only = {s.strip() for s in args.only.split(",")} if args.only else None
        result = run_once(cfg, send_mail=not args.no_mail, only=only)
        print((cfg.data_dir / "last_report.txt").read_text(encoding="utf-8"))
        return 0 if result.offers else 1
    elif args.command == "check":
        http = HttpClient(cfg.user_agent, cfg.min_delay, cfg.timeout, cfg.respect_robots)
        offers, results = collect(cfg, http, {args.source_id})
        if not results:
            print(f"nincs ilyen (engedélyezett) forrás: {args.source_id}")
            return 2
        for offer in sorted(offers, key=lambda o: (o.country, o.price)):
            print(f"{offer.country}  {fmt_money(offer.price, offer.currency):>14}  {offer.merchant:<28} "
                  f"{offer.variant:<18} {offer.url}")
        print(f"-- {results[0].status}: {results[0].offers} ajánlat {results[0].message}")
    elif args.command == "sources":
        adapters = load_adapters()
        for src in cfg.sources:
            state = "be" if src.enabled else "ki"
            known = "" if src.adapter in adapters else "  (ISMERETLEN ADAPTER!)"
            print(f"[{state}] {src.id:<28} adapter: {src.adapter}{known}")
    elif args.command == "test-mail":
        send(cfg.mail, "Surface árfigyelő – próbalevél",
             "<p>Ez egy próbalevél a Surface árfigyelőtől. Az SMTP-beállítás működik.</p>",
             "Ez egy próbalevél a Surface árfigyelőtől. Az SMTP-beállítás működik.")
        print(f"próbalevél elküldve: {', '.join(cfg.mail.recipients)} ({cfg.mail.host}:{cfg.mail.port})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
