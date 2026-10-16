"""Codzienny przebieg: scraping portali -> CSV -> import -> deduplikacja -> metryki.

Każde źródło (Otodom, Gratka, ...) działa osobno: blokada jednego nie zatrzymuje pozostałych.
Każde ma własny wpis w scrape.runs. Deduplikacja i metryki liczone raz, po wszystkich źródłach.

Kody wyjścia (dla crona / alertów; przy kilku źródłach najwyższy):
  0 ok, 1 błąd ogólny, 2 źródło niezatwierdzone, 3 blokada (403), 4 zmiana struktury strony,
  5 podejrzanie mało ogłoszeń w porównaniu z poprzednim przebiegiem.
"""
from __future__ import annotations

import csv
import fcntl
import json
import logging
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import db
from .scrapers import gratka, otodom
from .scrapers.http import Blocked, PoliteClient
from .scrapers.otodom_api import OtodomApi, load_cookie
from .scrapers.pg_cache import PgCache
from .synthetic import CSV_COLUMNS

log = logging.getLogger(__name__)
SOURCE_NAMES = {"otodom": "Otodom", "gratka": "Gratka"}
DEFAULT_SOURCES = ("otodom", "gratka")
DROP_ALERT_RATIO = 0.5
# Mało zapytań dziennie: po blokadzie IP (403) wolimy wolniejsze uzupełnianie niż kolejną blokadę.
HISTORY_BACKFILL_PER_RUN = 150  # ~300 zapytań API dziennie; ~3300 ofert uzupełni się w ok. 3 tygodnie


def _log_run(conn, source, started, status, rows=None, stats=None, message=None):
    conn.execute(
        """INSERT INTO scrape.runs (source_id, started_at, status, rows_written, stats, message)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (source, started, status, rows, json.dumps(asdict(stats)) if stats else None, message),
    )
    conn.commit()


def _previous_rows(conn, source) -> int | None:
    row = conn.execute(
        """SELECT rows_written FROM scrape.runs WHERE source_id = %s AND status IN ('ok', 'warning')
           ORDER BY run_id DESC LIMIT 1""",
        (source,),
    ).fetchone()
    return row[0] if row else None


def write_csv(rows: list[dict], out_dir: Path, observed_at: date, source: str = "otodom") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source}_{observed_at.isoformat()}.csv"
    if path.exists():  # drugi przebieg tego samego dnia
        path = out_dir / f"{source}_{observed_at.isoformat()}_{datetime.now():%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def already_done_today(conn, today: date, source: str = "otodom") -> bool:
    row = conn.execute(
        """SELECT 1 FROM scrape.runs WHERE source_id = %s AND status IN ('ok', 'warning')
           AND (started_at AT TIME ZONE 'Europe/Warsaw')::date = %s LIMIT 1""",
        (source, today),
    ).fetchone()
    return row is not None


class _SourceLock:
    """Blokada pliku per źródło: to samo źródło nie biegnie dwa razy naraz
    (np. długie pierwsze pobieranie i ponowna próba o 14:00). Działa między kontenerami,
    bo katalog data/ jest wspólny."""

    def __init__(self, out_dir: str | Path, source: str):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(out_dir) / f".{source}.lock"
        self.f = None

    def acquire(self) -> bool:
        self.f = self.path.open("w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self.f.close()
            self.f = None
            return False

    def release(self) -> None:
        if self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
            self.f = None


def configured_sources() -> tuple[str, ...]:
    raw = os.environ.get("LMI_SOURCES")
    return tuple(x.strip() for x in raw.split(",") if x.strip()) if raw else DEFAULT_SOURCES


def run_daily(conn, out_dir: str | Path = "data/raw", max_details: int | None = None,
              region_slug: str = "dolnoslaskie", teryt_prefix: str = "02",
              client: PoliteClient | None = None, observed_at: date | None = None,
              geo_client: PoliteClient | None = None, history_backfill: int = HISTORY_BACKFILL_PER_RUN,
              api: OtodomApi | None = None, if_needed: bool = False,
              sources: tuple[str, ...] | None = None) -> int:
    observed_at = observed_at or date.today()
    db.apply_schema(conn)
    client = client or PoliteClient()
    geo_client = geo_client or (PoliteClient(min_delay=0.3, max_delay=0.6) if isinstance(client, PoliteClient)
                                else client)
    codes, imported = [], False
    first_error: Exception | None = None
    for source in sources or configured_sources():
        if source not in SOURCE_NAMES:
            print(f"Nieznane źródło: {source}")
            codes.append(1)
            continue
        if if_needed and already_done_today(conn, observed_at, source):
            print(f"{SOURCE_NAMES[source]}: dzisiejsze pobieranie już się udało.")
            continue
        lock = _SourceLock(out_dir, source)
        if not lock.acquire():
            print(f"{SOURCE_NAMES[source]}: inny przebieg tego źródła jeszcze trwa, pomijam.")
            continue
        started = datetime.now(timezone.utc)
        try:
            code, did_import = _run_source(conn, source, out_dir, max_details, region_slug, teryt_prefix,
                                           client, observed_at, geo_client, history_backfill, api, started)
        except Exception as exc:  # każdy nieprzewidziany błąd zostaje w dzienniku i na stronie
            conn.rollback()
            _log_run(conn, source, started, "error", message=f"{type(exc).__name__}: {exc}"[:500])
            print(f"{SOURCE_NAMES[source]}: BŁĄD {type(exc).__name__}: {exc}")
            first_error = first_error or exc
            code, did_import = 1, False
        finally:
            lock.release()
        codes.append(code)
        imported = imported or did_import

    if imported:
        run_id, links = db.run_dedup(conn)
        _, scores = db.run_metrics(conn, run_id)
        print(f"Deduplikacja: {len(links)} ogłoszeń -> {len({l.property_key for l in links})} nieruchomości. "
              f"Metryki przeliczone ({len(scores)} gmin).")
    if first_error is not None and not imported:
        raise first_error
    return max(codes, default=0)


def _run_source(conn, source, out_dir, max_details, region_slug, teryt_prefix, client, observed_at,
                geo_client, history_backfill, api, started) -> tuple[int, bool]:
    name = SOURCE_NAMES[source]
    approved = conn.execute("SELECT approved FROM core.sources WHERE source_id = %s", (source,)).fetchone()
    if not approved or not approved[0]:
        print(f"Źródło '{source}' nie jest zatwierdzone. Uruchom raz:\n"
              f"  lmi add-source {source} {name}\n"
              f"  lmi approve-source {source} --legal-basis '...' --approved-by '...'")
        return 2, False

    try:
        if source == "otodom":
            if api is None and isinstance(client, PoliteClient):
                cookie = load_cookie()
                api = OtodomApi(client.get, cookie) if cookie else None
            print("Historia ofert z konta Otodom:", "włączona" if api else "wyłączona (brak pliku z ciasteczkiem)")
            rows, stats = otodom.scrape(client.get, PgCache(conn), observed_at, region_slug=region_slug,
                                        teryt_prefix=teryt_prefix, max_details=max_details,
                                        geo_get=geo_client.get, api=api, history_backfill=history_backfill)
        else:
            rows, stats = gratka.scrape(client.get, PgCache(conn, source), observed_at, region_slug=region_slug,
                                        teryt_prefix=teryt_prefix, max_details=max_details, geo_get=geo_client.get)
    except Blocked as exc:
        _log_run(conn, source, started, "blocked", message=str(exc))
        print(f"{name}: BLOKADA: {exc}. Przerwano bez ponawiania.")
        return 3, False
    except otodom.LayoutChanged as exc:
        _log_run(conn, source, started, "layout_changed", message=str(exc))
        print(f"{name}: ZMIANA STRUKTURY STRONY: {exc}. Parser wymaga poprawki.")
        return 4, False

    print(f"{name}: {stats.pages} stron, {stats.unique_ads} ogłoszeń, {stats.rows} wierszy "
          f"(nowe szczegóły {stats.details_fetched}, odłożone {stats.details_deferred}, "
          f"bez ceny {stats.skipped_no_price}, bez lokalizacji {stats.skipped_no_location}, "
          f"poza regionem {stats.skipped_outside_region})")
    if stats.land_use_filled:
        print(f"Rodzaj działki uzupełniony z tytułu/opisu: {stats.land_use_filled} "
              f"(ponownie pobranych stron: {stats.land_use_refetched})")
    if source == "otodom" and api is not None:
        print(f"Historia: nowe {stats.history_fetched}, uzupełnione {stats.history_backfilled}, "
              f"błędy {stats.history_failed}")
    if not rows:
        _log_run(conn, source, started, "error", 0, stats, "0 wierszy")
        print(f"{name}: BŁĄD: 0 wierszy.")
        return 1, False

    path = write_csv(rows, Path(out_dir) / source, observed_at, source)
    result = db.import_csv(conn, source, path)
    print(f"{name}: import {path} -> dodano {result.rows_inserted}, duplikatów {result.rows_duplicate}")

    previous = _previous_rows(conn, source)
    if previous and stats.details_deferred == 0 and len(rows) < DROP_ALERT_RATIO * previous:
        msg = f"liczba wierszy spadła z {previous} do {len(rows)}"
        _log_run(conn, source, started, "warning", len(rows), stats, msg)
        print(f"{name}: OSTRZEŻENIE: {msg} — sprawdź, czy parser działa poprawnie.")
        return 5, True
    if stats.session_expired:
        msg = "Sesja konta Otodom wygasła: historia ofert nie jest pobierana. Odśwież ciasteczko (deploy/README.md)."
        _log_run(conn, source, started, "warning", len(rows), stats, msg)
        print("OSTRZEŻENIE:", msg)
        return 0, True
    _log_run(conn, source, started, "ok", len(rows), stats)
    return 0, True


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
