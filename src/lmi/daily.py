"""Codzienny przebieg: scraping Otodom -> CSV -> import -> deduplikacja -> metryki.

Kody wyjścia (dla crona / alertów):
  0 ok, 1 błąd ogólny, 2 źródło niezatwierdzone, 3 blokada (403), 4 zmiana struktury strony,
  5 podejrzanie mało ogłoszeń w porównaniu z poprzednim przebiegiem.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import db
from .scrapers import otodom
from .scrapers.http import Blocked, PoliteClient
from .scrapers.otodom_api import OtodomApi, load_cookie
from .scrapers.pg_cache import PgCache
from .synthetic import CSV_COLUMNS

log = logging.getLogger(__name__)
SOURCE_ID = "otodom"
DROP_ALERT_RATIO = 0.5
HISTORY_BACKFILL_PER_RUN = 600  # ~1 h dziennie; ~4100 ofert uzupełni się w ok. tydzień


def _log_run(conn, started, status, rows=None, stats=None, message=None):
    conn.execute(
        """INSERT INTO scrape.runs (source_id, started_at, status, rows_written, stats, message)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (SOURCE_ID, started, status, rows, json.dumps(asdict(stats)) if stats else None, message),
    )
    conn.commit()


def _previous_rows(conn) -> int | None:
    row = conn.execute(
        """SELECT rows_written FROM scrape.runs WHERE source_id = %s AND status IN ('ok', 'warning')
           ORDER BY run_id DESC LIMIT 1""",
        (SOURCE_ID,),
    ).fetchone()
    return row[0] if row else None


def write_csv(rows: list[dict], out_dir: Path, observed_at: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{SOURCE_ID}_{observed_at.isoformat()}.csv"
    if path.exists():  # drugi przebieg tego samego dnia
        path = out_dir / f"{SOURCE_ID}_{observed_at.isoformat()}_{datetime.now():%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def run_daily(conn, out_dir: str | Path = "data/raw", max_details: int | None = None,
              region_slug: str = "dolnoslaskie", teryt_prefix: str = "02",
              client: PoliteClient | None = None, observed_at: date | None = None,
              geo_client: PoliteClient | None = None, history_backfill: int = HISTORY_BACKFILL_PER_RUN,
              api: OtodomApi | None = None) -> int:
    started = datetime.now(timezone.utc)
    observed_at = observed_at or date.today()
    db.apply_schema(conn)

    approved = conn.execute("SELECT approved FROM core.sources WHERE source_id = %s", (SOURCE_ID,)).fetchone()
    if not approved or not approved[0]:
        print(f"Źródło '{SOURCE_ID}' nie jest zatwierdzone. Uruchom raz:\n"
              f"  lmi add-source {SOURCE_ID} Otodom\n"
              f"  lmi approve-source {SOURCE_ID} --legal-basis '...' --approved-by '...'")
        return 2

    client = client or PoliteClient()
    geo_client = geo_client or (PoliteClient(min_delay=0.3, max_delay=0.6) if isinstance(client, PoliteClient)
                                else client)
    if api is None and isinstance(client, PoliteClient):
        cookie = load_cookie()
        api = OtodomApi(client.get, cookie) if cookie else None
    print("Historia ofert z konta Otodom:", "włączona" if api else "wyłączona (brak pliku z ciasteczkiem)")
    try:
        rows, stats = otodom.scrape(client.get, PgCache(conn), observed_at, region_slug=region_slug,
                                    teryt_prefix=teryt_prefix, max_details=max_details,
                                    geo_get=geo_client.get, api=api, history_backfill=history_backfill)
    except Blocked as exc:
        _log_run(conn, started, "blocked", message=str(exc))
        print(f"BLOKADA: {exc}. Przerwano bez ponawiania.")
        return 3
    except otodom.LayoutChanged as exc:
        _log_run(conn, started, "layout_changed", message=str(exc))
        print(f"ZMIANA STRUKTURY STRONY: {exc}. Parser wymaga poprawki.")
        return 4

    print(f"Otodom: {stats.pages} stron, {stats.unique_ads} ogłoszeń, {stats.rows} wierszy "
          f"(nowe szczegóły {stats.details_fetched}, odłożone {stats.details_deferred}, "
          f"bez ceny {stats.skipped_no_price}, bez lokalizacji {stats.skipped_no_location}, "
          f"poza regionem {stats.skipped_outside_region}); zapytań HTTP: {client.requests_made}")
    if stats.land_use_filled:
        print(f"Rodzaj działki uzupełniony z tytułu/opisu: {stats.land_use_filled} "
              f"(ponownie pobranych stron: {stats.land_use_refetched})")
    if api is not None:
        print(f"Historia: nowe {stats.history_fetched}, uzupełnione {stats.history_backfilled}, "
              f"błędy {stats.history_failed}")
    if not rows:
        _log_run(conn, started, "error", 0, stats, "0 wierszy")
        print("BŁĄD: 0 wierszy.")
        return 1

    path = write_csv(rows, Path(out_dir) / SOURCE_ID, observed_at)
    result = db.import_csv(conn, SOURCE_ID, path)
    print(f"Import: {path} -> dodano {result.rows_inserted}, duplikatów {result.rows_duplicate}")
    run_id, links = db.run_dedup(conn)
    _, scores = db.run_metrics(conn, run_id)
    print(f"Deduplikacja: {len(links)} ogłoszeń -> {len({l.property_key for l in links})} nieruchomości. "
          f"Metryki przeliczone ({len(scores)} gmin).")

    previous = _previous_rows(conn)
    if previous and stats.details_deferred == 0 and len(rows) < DROP_ALERT_RATIO * previous:
        msg = f"liczba wierszy spadła z {previous} do {len(rows)}"
        _log_run(conn, started, "warning", len(rows), stats, msg)
        print(f"OSTRZEŻENIE: {msg} — sprawdź, czy parser działa poprawnie.")
        return 5
    if stats.session_expired:
        msg = "Sesja konta Otodom wygasła: historia ofert nie jest pobierana. Odśwież ciasteczko (deploy/README.md)."
        _log_run(conn, started, "warning", len(rows), stats, msg)
        print("OSTRZEŻENIE:", msg)
        return 0
    _log_run(conn, started, "ok", len(rows), stats)
    return 0


def check_otodom(region_slug: str = "dolnoslaskie", details: int = 3) -> int:
    """Szybki test bez bazy: 1 strona wyników + kilka ofert + ULDK. Wypisuje tylko liczby."""
    from .scrapers import uldk

    client = PoliteClient()
    items, pages = otodom.parse_search_page(client.get(otodom.SEARCH_URL.format(region=region_slug, page=1)))
    with_price = sum(1 for i in items if i.price_pln)
    with_area = sum(1 for i in items if i.area_m2)
    print(f"Wyniki: {len(items)} ogłoszeń na stronie 1, stron: {pages}, z ceną: {with_price}, z metrażem: {with_area}")
    ok = bool(items) and with_price > 0 and with_area > 0
    for it in items[:details]:
        d = otodom.parse_detail_page(client.get(otodom.DETAIL_URL.format(slug=it.slug)))
        commune = None
        if d["lat"] is not None:
            commune = uldk.parse_commune_response(client.get(uldk.commune_url(d["lat"], d["lon"])))
        print(f"  ad {it.ad_id}: cena={it.price_pln} m2={it.area_m2 or d['area_m2']} "
              f"lat={d['lat']} lon={d['lon']} dokładna={d['precise']} typ={d['land_use']} "
              f"gmina={commune}")
        ok = ok and d["lat"] is not None and commune is not None
    print("WYNIK:", "OK" if ok else "PROBLEM — wklej ten wynik do czatu")
    return 0 if ok else 1
