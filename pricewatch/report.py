"""Builds the daily e-mail (HTML + plain text, in Hungarian)."""
from __future__ import annotations

from html import escape

from .config import Config
from .models import COUNTRIES, Offer, RunResult
from .storage import Storage

_SPARK = "▁▂▃▄▅▆▇█"
_STATUS_HU = {
    "ok": ("rendben", "#1a7f37"),
    "empty": ("nincs találat", "#9a6700"),
    "blocked": ("letiltva (bot-védelem)", "#cf222e"),
    "robots": ("robots.txt tiltja", "#cf222e"),
    "error": ("hiba", "#cf222e"),
}


def fmt_money(amount: float, currency: str) -> str:
    if currency == "HUF":
        return f"{amount:,.0f}".replace(",", " ") + " Ft"
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {'€' if currency == 'EUR' else currency}"


def sparkline(values: list[float]) -> str:
    if not values:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return _SPARK[3] * len(values)
    return "".join(_SPARK[min(len(_SPARK) - 1, int((v - low) / (high - low) * len(_SPARK)))] for v in values)


def rank_value(offer: Offer, rank_by: str) -> float:
    return offer.total() if rank_by == "total" else offer.price


def select_top(offers: list[Offer], cfg: Config) -> dict[str, list[Offer]]:
    top: dict[str, list[Offer]] = {}
    for country in cfg.countries:
        ranked = sorted((o for o in offers if o.country == country),
                        key=lambda o: (rank_value(o, cfg.rank_by),
                                       o.shipping if o.shipping is not None else float("inf"),
                                       o.merchant_key))  # equal price: cheaper known shipping first
        chosen: list[Offer] = []
        seen: set[str] = set()
        for offer in ranked:
            if cfg.distinct_merchants and offer.merchant_key in seen:
                continue
            seen.add(offer.merchant_key)
            chosen.append(offer)
            if len(chosen) == cfg.top_n:
                break
        top[country] = chosen
    return top


def _delta(current: float, previous: float | None, currency: str) -> tuple[str, str]:
    """(text, colour) describing the change since the previous day."""
    if previous is None:
        return "új", "#57606a"
    diff = current - previous
    if abs(diff) < 0.005:
        return "változatlan", "#57606a"
    pct = diff / previous * 100
    arrow, colour = ("▼", "#1a7f37") if diff < 0 else ("▲", "#cf222e")
    sign = "−" if diff < 0 else "+"
    return f"{arrow} {sign}{fmt_money(abs(diff), currency)} ({sign}{abs(pct):.1f}%)".replace(".", ","), colour


def build_report(result: RunResult, cfg: Config, storage: Storage) -> tuple[str, str, str]:
    top = select_top(result.offers, cfg)
    prev_id = storage.previous_run_id(result.run_id)
    prev_prices = storage.merchant_prices(prev_id) if prev_id else {}
    prev_min = storage.country_min(prev_id) if prev_id else {}

    subject_bits = []
    for country in cfg.countries:
        best = top[country][0] if top[country] else None
        subject_bits.append(f"{country} {fmt_money(best.price, best.currency)}" if best else f"{country} –")
    subject = f"Surface Pro 11 árfigyelő {result.run_date}: " + " | ".join(subject_bits)
    subject = subject.replace(" ", " ")

    html: list[str] = [
        '<html><body style="margin:0;padding:16px;background:#f6f8fa;font-family:Segoe UI,Arial,sans-serif;'
        'color:#1f2328;font-size:14px;">',
        '<div style="max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #d0d7de;'
        'border-radius:8px;padding:20px;">',
        f'<h2 style="margin:0 0 4px 0;">{escape(cfg.product_name)}</h2>',
        f'<div style="color:#57606a;margin-bottom:16px;">Napi árjelentés – {result.run_date} · '
        f'{len(result.offers)} ajánlat {sum(1 for s in result.sources if s.status == "ok")} forrásból</div>',
    ]
    text: list[str] = [cfg.product_name, f"Napi árjelentés – {result.run_date}", ""]

    # ---- per-country top offers
    for country in cfg.countries:
        name, flag, _ = COUNTRIES[country]
        count = sum(1 for o in result.offers if o.country == country)
        html.append(f'<h3 style="margin:18px 0 6px 0;border-bottom:2px solid #d0d7de;padding-bottom:4px;">'
                    f'{flag} {name} <span style="font-weight:normal;color:#57606a;font-size:12px;">'
                    f'({count} ajánlat)</span></h3>')
        text.append(f"== {name} ({count} ajánlat) ==")
        if not top[country]:
            html.append('<div style="color:#9a6700;">Ma nem találtam megfelelő ajánlatot ebben az országban.</div>')
            text += ["  Ma nem találtam megfelelő ajánlatot.", ""]
            continue
        html.append('<table cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;">')
        for rank, offer in enumerate(top[country], start=1):
            previous = prev_prices.get(offer.dedup_key)
            delta, colour = _delta(offer.price, previous, offer.currency)
            eur = ""
            if offer.currency != "EUR" and offer.price_eur:
                eur = f' <span style="color:#57606a;font-size:12px;">≈ {fmt_money(offer.price_eur, "EUR")}</span>'
            extras = [escape(x) for x in (offer.variant, _shipping(offer), offer.availability) if x]
            html.append(
                f'<tr style="border-bottom:1px solid #eaeef2;vertical-align:top;">'
                f'<td style="width:22px;color:#57606a;">{rank}.</td>'
                f'<td style="white-space:nowrap;"><b style="font-size:16px;">{fmt_money(offer.price, offer.currency)}</b>'
                f'{eur}<br><span style="color:{colour};font-size:12px;">{delta}</span></td>'
                f'<td><a href="{escape(offer.url, quote=True)}" style="color:#0969da;font-weight:600;'
                f'text-decoration:none;">{escape(offer.merchant)}</a><br>'
                f'<span style="font-size:12px;">{escape(offer.title[:110])}</span><br>'
                f'<span style="color:#57606a;font-size:12px;">{" · ".join(extras)}'
                f'{" · " if extras else ""}forrás: {escape(offer.source)}</span><br>'
                f'<span style="font-size:12px;"><b>Átvétel:</b> {escape(" · ".join(offer.delivery.lines_hu()))}'
                f'</span>{_financing_html(offer, country)}</td></tr>'
            )
            text.append(f"  {rank}. {fmt_money(offer.price, offer.currency)}  {offer.merchant}  [{delta}]")
            text.append(f"     {offer.title[:100]}")
            text.append(f"     Átvétel: {' · '.join(offer.delivery.lines_hu())}")
            if country == "HU" or offer.financing.known():
                text.append(f"     Részletfizetés: {offer.financing.line_hu()}")
            text.append(f"     {offer.url}")
        html.append("</table>")
        if country == "HU":
            best_zero = min((o for o in result.offers if o.country == "HU" and o.financing.thm0 == "yes"),
                            key=lambda o: o.price, default=None)
            if best_zero is None:
                note = "Ma egyik magyar ajánlatnál sem találtam erre a termékre kimondott 0% THM-es konstrukciót."
                html.append(f'<div style="font-size:12px;margin-top:6px;color:#9a6700;">{note}</div>')
            else:
                note = (f"Legolcsóbb 0% THM-es magyar ajánlat: {best_zero.merchant} – "
                        f"{fmt_money(best_zero.price, best_zero.currency)} ({best_zero.financing.terms})")
                html.append(f'<div style="font-size:13px;margin-top:6px;background:#dafbe1;padding:6px 8px;'
                            f'border-radius:6px;"><b>Legolcsóbb 0% THM-es magyar ajánlat:</b> '
                            f'<a href="{escape(best_zero.url, quote=True)}" style="color:#0969da;">'
                            f'{escape(best_zero.merchant)}</a> – {fmt_money(best_zero.price, best_zero.currency)} '
                            f'({escape(best_zero.financing.terms)})</div>')
            text.append("  " + note.replace(" ", " "))
        text.append("")

    html.append('<div style="color:#57606a;font-size:11px;margin-top:8px;">Átvétel: az ár-összehasonlítók és a boltok '
                'saját oldalai alapján. „Csomagpont: lehetséges” = a bolt olyan futárszolgálattal szállít, amelynek van '
                'csomagpont-hálózata; hogy oda kérhető-e a csomag, a bolt pénztáránál derül ki. '
                '„Nincs adat” = a forrás nem közli.<br>Részletfizetés (magyar boltok): „igen” = a bolt erre a termékre, '
                'illetve erre a kosárértékre 0% THM-es konstrukciót hirdet (hitelbírálat után); „lehetséges” = a bolt '
                'csak megjelölt termékekre ad 0% THM-et, a terméklapon kell ellenőrizni; „nincs” = a bolt tájékoztatója '
                'szerint csak kamatos konstrukció érhető el.</div>')

    # ---- cross-country comparison + trend
    html.append('<h3 style="margin:22px 0 6px 0;border-bottom:2px solid #d0d7de;padding-bottom:4px;">'
                'Ártrend országonként (legolcsóbb ajánlat)</h3>')
    html.append('<table cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px;">'
                '<tr style="text-align:left;color:#57606a;"><th>Ország</th><th>Ma</th><th>≈ EUR</th>'
                '<th>Előző nap</th><th>30 napos min.</th><th>Eddigi legalacsonyabb</th><th>30 nap</th></tr>')
    text.append("== Ártrend (legolcsóbb ajánlat országonként) ==")
    for country in cfg.countries:
        name, flag, currency = COUNTRIES[country]
        best = top[country][0] if top[country] else None
        history = storage.daily_minimums(country, 30)
        low30 = min((p for _, p in history), default=None)
        all_low = storage.all_time_low(country)
        today = fmt_money(best.price, best.currency) if best else "–"
        eur = fmt_money(best.price_eur, "EUR") if best and best.price_eur and best.currency != "EUR" else "–"
        if best and country in prev_min:
            delta, colour = _delta(best.price, prev_min[country], best.currency)
        else:
            delta, colour = ("–", "#57606a")
        low_text = (f"{fmt_money(all_low[0], currency)}<br><span style='color:#57606a;font-size:11px;'>"
                    f"{all_low[1]}, {escape(all_low[2])}</span>") if all_low else "–"
        html.append(
            f'<tr style="border-top:1px solid #eaeef2;vertical-align:top;"><td>{flag} {name}</td>'
            f'<td><b>{today}</b></td><td>{eur}</td><td style="color:{colour};">{delta}</td>'
            f'<td>{fmt_money(low30, currency) if low30 else "–"}</td><td>{low_text}</td>'
            f'<td style="font-family:monospace;letter-spacing:1px;">{sparkline([p for _, p in history])}</td></tr>'
        )
        text.append(f"  {name}: ma {today}" + (f" (≈ {eur})" if eur != "–" else "") + f", előző naphoz: {delta}"
                    + (f", eddigi min.: {fmt_money(all_low[0], currency)} ({all_low[1]})" if all_low else ""))
    html.append("</table>")
    html.append(f'<div style="color:#57606a;font-size:11px;margin-top:4px;">Átváltás: {escape(result.fx_note)}. '
                f'Az árak az adott ország bruttó (áfás) árai, szállítás nélkül.</div>')
    text += ["", f"Átváltás: {result.fx_note}.", ""]

    # ---- source health
    problems = [s for s in result.sources if s.status != "ok"]
    html.append('<h3 style="margin:22px 0 6px 0;border-bottom:2px solid #d0d7de;padding-bottom:4px;">'
                f'Források állapota <span style="font-weight:normal;color:#57606a;font-size:12px;">'
                f'({len(result.sources) - len(problems)} rendben, {len(problems)} problémás)</span></h3>')
    html.append('<table cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:12px;">')
    text.append("== Források állapota ==")
    for status in sorted(result.sources, key=lambda s: (s.status == "ok", s.source_id)):
        label, colour = _STATUS_HU.get(status.status, (status.status, "#57606a"))
        html.append(
            f'<tr style="border-top:1px solid #eaeef2;"><td>{escape(status.source_id)}</td>'
            f'<td style="color:{colour};white-space:nowrap;">{label}</td><td>{status.offers} ajánlat</td>'
            f'<td style="color:#57606a;">{escape(status.message[:160])}</td></tr>'
        )
        text.append(f"  {status.source_id}: {label}, {status.offers} ajánlat {status.message[:120]}".rstrip())
    html.append("</table>")
    html.append('<div style="color:#8c959f;font-size:11px;margin-top:18px;">Surface árfigyelő – '
                'automatikus napi jelentés a NAS-ról.</div></div></body></html>')

    return subject, "\n".join(html), "\n".join(text).replace(" ", " ")


def _financing_html(offer: Offer, country: str) -> str:
    """Instalment line – always shown for Hungarian offers, elsewhere only when something is known."""
    if country != "HU" and not offer.financing.known():
        return ""
    colour = {"yes": "#1a7f37", "no": "#57606a"}.get(offer.financing.thm0, "#1f2328")
    return (f'<br><span style="font-size:12px;color:{colour};"><b>Részletfizetés:</b> '
            f'{escape(offer.financing.line_hu())}</span>')


def _shipping(offer: Offer) -> str:
    if offer.shipping is None:
        return ""
    if offer.shipping == 0:
        return "ingyenes szállítás"
    return f"szállítás: {fmt_money(offer.shipping, offer.currency)}"
