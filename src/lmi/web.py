"""Strona Radar Działek: API na danych z bazy + statyczny frontend (web_static/).

Uruchomienie: uvicorn lmi.web:app --host 0.0.0.0 --port 8080
Dostęp chroni Traefik (hasło na wejściu), aplikacja sama nie ma logowania.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

from .db import DEFAULT_DSN
from .metrics import MIN_SUPPLY_FOR_RANK, SEGMENTS

STATIC = Path(__file__).parent / "web_static"

app = FastAPI(title="Radar Działek", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
# adres strony w domenie, np. "/radar/" (podstrona); "/" = katalog główny domeny. Strona używa adresów względnych,
# więc działa pod każdą ścieżką; to ustawienie potrzebne jest tylko do powrotu po wylogowaniu.
BASE_PATH = "/" + os.environ.get("LMI_BASE_PATH", "").strip("/") + "/" if os.environ.get("LMI_BASE_PATH", "").strip("/") else "/"


def _conn():
    return psycopg.connect(os.environ.get("LMI_DATABASE_URL", DEFAULT_DSN), row_factory=dict_row)


def _rows(sql: str, params: dict | None = None) -> list[dict]:
    with _conn() as conn:
        return conn.execute(sql, params or {}).fetchall()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz", include_in_schema=False)
def healthz():
    _rows("SELECT 1")
    return {"ok": True}


TEAM_USER = "zespół"  # przy wspólnym haśle (bez logowania Google) wszyscy są jednym użytkownikiem


def _user(request: Request) -> str:
    """Kto korzysta ze strony. Nagłówki ustawia Traefik: X-Auth-Request-Email z logowania Google
    (oauth2-proxy), X-Auth-Request-User z bramki z hasłem (login osoby). Bez nich: wspólny „zespół”."""
    who = request.headers.get("x-auth-request-email") or request.headers.get("x-auth-request-user")
    return (who or TEAM_USER).strip().lower()


def _admins() -> set[str]:
    """Kto widzi zgłoszenia: LMI_ADMINS w .env (loginy z bramki albo e-maile Google, po przecinku)."""
    return {a.strip().lower() for a in os.environ.get("LMI_ADMINS", "").split(",") if a.strip()}


def _is_admin(request: Request) -> bool:
    """LMI_ADMINS albo poziom „admin” w obszarze radar z panelu Administracja (nagłówek ustawia Traefik –
    ufamy mu tylko, gdy router ma middleware wre-radar: LMI_UPRAWNIENIA_Z_NAGLOWKA=1)."""
    if os.environ.get("LMI_UPRAWNIENIA_Z_NAGLOWKA") == "1" and request.headers.get("x-pracawre-poziom") == "admin":
        return True
    return _user(request) in _admins()


def _require_admin(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(403, "tylko dla administratora")


@app.get("/api/me")
def me(request: Request):
    email = request.headers.get("x-auth-request-email")
    return {"email": email, "user": _user(request), "is_admin": _is_admin(request),
            # logowanie jest wspólne dla domeny (/oauth2 w katalogu głównym); po wylogowaniu wracamy na podstronę
            "logout_url": "/oauth2/sign_out?rd=" + quote(BASE_PATH, safe="") if email else None}


SEGMENT_DEFAULT = "budowlana"


def _segment(use: str | None) -> str:
    """Typ działek dla metryk: 'budowlana' (domyślnie), 'wszystkie' albo inny z metrics.SEGMENTS."""
    use = use or SEGMENT_DEFAULT
    if use not in SEGMENTS:
        raise HTTPException(400, f"use: jeden z {', '.join(SEGMENTS)}")
    return use


@app.get("/api/overview")
def overview(use: str | None = None):
    seg = _segment(use)
    run = _rows("""SELECT finished_at, status, rows_written, message FROM scrape.runs
                   WHERE status IN ('ok', 'warning') ORDER BY run_id DESC LIMIT 1""")
    attempt = _rows("""SELECT started_at, finished_at, status, message FROM scrape.runs
                       ORDER BY run_id DESC LIMIT 1""")
    # stan każdego źródła: ostatni udany przebieg i ostatnia próba
    per_source = _rows("""
        SELECT s.source_id AS source, s.name,
               (SELECT finished_at FROM scrape.runs r WHERE r.source_id = s.source_id
                  AND r.status IN ('ok', 'warning') ORDER BY run_id DESC LIMIT 1) AS last_ok,
               (SELECT json_build_object('started_at', started_at, 'status', status, 'message', message)
                  FROM scrape.runs r WHERE r.source_id = s.source_id ORDER BY run_id DESC LIMIT 1) AS latest
        FROM core.sources s WHERE s.approved ORDER BY s.source_id""")
    weekly = _rows("""
        SELECT count(DISTINCT week_start) AS weeks,
               max(week_start) AS last_week
        FROM mart.weekly_region_metrics WHERE segment = %(s)s""", {"s": seg})[0]
    latest = _rows("""
        SELECT coalesce(sum(active_supply), 0) AS active_offers,
               coalesce(sum(new_listings), 0)  AS new_this_week,
               count(*) FILTER (WHERE active_supply > 0) AS municipalities
        FROM mart.weekly_region_metrics
        WHERE segment = %(s)s AND week_start = (SELECT max(week_start) FROM mart.weekly_region_metrics)""",
                   {"s": seg})[0]
    last_day = _rows("SELECT max(observed_at) AS d FROM core.listing_observations")[0]["d"]
    return {
        "last_run": run[0] if run else None,          # ostatni udany przebieg
        "latest_attempt": attempt[0] if attempt else None,  # ostatnia próba, także nieudana
        "sources": per_source,
        "last_observed": last_day,
        "weeks_of_data": weekly["weeks"],
        "last_week": weekly["last_week"],
        "min_supply_for_rank": MIN_SUPPLY_FOR_RANK,
        "segment": seg, "segments": list(SEGMENTS),
        **latest,
    }


@app.get("/api/ranking")
def ranking(use: str | None = None):
    seg = _segment(use)
    return _rows("""
        SELECT municipality_teryt AS teryt, municipality_name AS name, rank, opportunity_score AS score,
               avg_absorption_rate AS absorption, price_trend_pct AS price_trend,
               avg_discounted_share AS discounted, median_days_to_disappear AS days,
               latest_active_supply AS supply, latest_median_price_per_m2 AS ppm2, weeks_observed AS weeks,
               latest_median_listing_age_days AS age, t.tx_12m, t.tx_build_12m, t.tx_ppm2, t.tx_until,
               g.permits_12m, g.permits_prev_12m
        FROM mart.region_scores
        LEFT JOIN (
            -- transakcje samym gruntem z 12 miesięcy przed ostatnim aktem w powiecie (starostwa przekazują
            -- dane do RCN z różnym opóźnieniem); mediana z gruntów pod zabudowę, a gdy jest ich mniej niż 5
            -- (np. w mieście plan rzadko jest wpisany w akt) — ze wszystkich
            SELECT t.gmina_teryt, count(*) AS tx_12m, count(*) FILTER (WHERE buildable) AS tx_build_12m,
                   CASE WHEN count(*) FILTER (WHERE buildable) >= 5
                        THEN percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2) FILTER (WHERE buildable)
                        ELSE percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2) END AS tx_ppm2,
                   max(pl.d) AS tx_until
            FROM mart.rcn_land_transactions t
            JOIN (SELECT left(parcel_id, 4) AS pw, max(doc_date) AS d FROM scrape.rcn_parcels GROUP BY 1) pl
              ON pl.pw = left(t.gmina_teryt, 4)
            WHERE ppm2 BETWEEN %(lo)s AND %(hi)s AND doc_date > pl.d - 365
            GROUP BY t.gmina_teryt
        ) t ON t.gmina_teryt = municipality_teryt
        LEFT JOIN (
            -- pozwolenia na budowę domów jednorodzinnych (GUNB): ostatnie 12 miesięcy i poprzednie 12
            SELECT gmina_teryt,
                   count(*) FILTER (WHERE decided_on > x.m - 365) AS permits_12m,
                   count(*) FILTER (WHERE decided_on > x.m - 730 AND decided_on <= x.m - 365) AS permits_prev_12m
            FROM mart.gunb_permits, (SELECT max(decided_on) AS m FROM mart.gunb_permits) x
            WHERE single_family
            GROUP BY gmina_teryt
        ) g ON g.gmina_teryt = municipality_teryt
        WHERE segment = %(seg)s
        ORDER BY rank NULLS LAST, latest_active_supply DESC NULLS LAST, municipality_name""",
                 {**PPM2_RANGE, "seg": seg})


# --- co się zmieniło: województwo dzień po dniu i tydzień po tygodniu -------------------------------

# Tabele robocze liczone raz na przeliczenie (w jednej transakcji), potem zapytania dla każdego okresu.
CHANGES_TEMP = [
    "DROP VIEW IF EXISTS ch_lst, ch_prop, ch_pday",
    "DROP TABLE IF EXISTS ch_links, ch_src_start, chb_lst, chb_prop, chb_pday, ch_ptype",
    """CREATE TEMP TABLE ch_links ON COMMIT DROP AS
       SELECT source_id, source_listing_id, property_key FROM core.listing_property_links
       WHERE run_id = (SELECT max(run_id) FROM core.dedup_runs)""",
    """CREATE TEMP TABLE ch_src_start ON COMMIT DROP AS
       SELECT source_id, min(observed_at) AS s, max(observed_at) AS e FROM core.listing_observations GROUP BY 1""",
    """CREATE TEMP TABLE chb_lst ON COMMIT DROP AS
       SELECT o.source_id, l.property_key, min(o.observed_at) AS fs, max(o.observed_at) AS ls
       FROM core.listing_observations o JOIN ch_links l USING (source_id, source_listing_id) GROUP BY 1, 2""",
    """CREATE TEMP TABLE chb_prop ON COMMIT DROP AS
       WITH p0 AS (SELECT property_key, min(fs) AS fs, max(ls) AS ls FROM chb_lst GROUP BY 1)
       SELECT p0.property_key, p0.fs, p0.ls,
              -- nowa naprawdę, a nie pierwsze pobranie świeżo dodanego portalu
              coalesce(bool_and(l.fs > ss.s) FILTER (WHERE l.fs = p0.fs), false) AS genuine_new,
              -- zniknęła: żaden z jej portali jej już nie pokazał, choć pobierały się później
              bool_or(ss.e > p0.ls) AS gone_known
       FROM p0 JOIN chb_lst l USING (property_key) JOIN ch_src_start ss USING (source_id)
       GROUP BY 1, 2, 3""",
    """CREATE TEMP TABLE chb_pday ON COMMIT DROP AS
       SELECT property_key, d, price, area, teryt, gmina, url,
              lag(price) OVER (PARTITION BY property_key ORDER BY d) AS prev_price
       FROM (SELECT l.property_key, o.observed_at AS d, min(o.price_pln) AS price, max(o.area_m2) AS area,
                    (array_agg(o.municipality_teryt))[1] AS teryt, (array_agg(o.municipality_name))[1] AS gmina,
                    (array_agg(o.url ORDER BY o.source_id))[1] AS url
             FROM core.listing_observations o JOIN ch_links l USING (source_id, source_listing_id)
             GROUP BY 1, 2) x""",
    # typ działki: najczęstszy w jej ogłoszeniach (portale czasem różnie nazywają tę samą działkę)
    """CREATE TEMP TABLE ch_ptype ON COMMIT DROP AS
       SELECT l.property_key, mode() WITHIN GROUP (ORDER BY o.land_use) AS land_use
       FROM core.listing_observations o JOIN ch_links l USING (source_id, source_listing_id)
       WHERE o.land_use IS NOT NULL GROUP BY 1""",
    "CREATE INDEX ON chb_pday (d)",
    "CREATE INDEX ON chb_pday (property_key, d)",
    "CREATE INDEX ON ch_ptype (land_use, property_key)",
    "ANALYZE chb_pday",
    "ANALYZE chb_prop",
    "ANALYZE ch_ptype",
]


def _segment_views(conn, seg: str) -> None:
    """ch_lst / ch_prop / ch_pday: tabele robocze zawężone do jednego typu działek (widoki, bez kopiowania)."""
    conn.execute("DROP VIEW IF EXISTS ch_lst, ch_prop, ch_pday")
    for name in ("lst", "prop", "pday"):
        if seg == "wszystkie":
            q = sql.SQL("CREATE TEMP VIEW {} AS SELECT * FROM {}")
        else:
            q = sql.SQL("CREATE TEMP VIEW {} AS SELECT * FROM {} WHERE property_key IN "
                        "(SELECT property_key FROM ch_ptype WHERE land_use = {})")
        conn.execute(q.format(sql.Identifier(f"ch_{name}"), sql.Identifier(f"chb_{name}"), sql.Literal(seg)))


# transakcje RCN do porównania z ofertami danego typu
def _rcn_filter(seg: str) -> str:
    if seg == "wszystkie":
        return "true"
    return "NOT buildable" if seg in ("rolna", "leśna") else "buildable"

PERIODS = (1, 7, 30)
_CHANGES_LOCK = threading.Lock()


# Ostatni pełny dzień: taki, w którym pobrały się już wszystkie portale aktywne w ostatnim tygodniu.
# W trakcie porannego przebiegu (Otodom już jest, reszta jeszcze nie) strona pokazuje wczoraj, a nie pół dnia.
COMPLETE_DAY = """
    WITH ends AS (SELECT source_id, max(observed_at) AS e FROM core.listing_observations GROUP BY 1)
    SELECT min(e) AS d FROM ends WHERE e >= (SELECT max(e) FROM ends) - 7"""


def _changes_state(conn) -> str:
    r = conn.execute(f"""SELECT ({COMPLETE_DAY}) AS d,
                               (SELECT max(run_id) FROM core.dedup_runs) AS run,
                               (SELECT max(fetched_at) FROM scrape.rcn_fetch_log) AS rcn,
                               (SELECT max(fetched_at) FROM scrape.gunb_fetch_log) AS gunb""").fetchone()
    return f"{r['d']}|{r['run']}|{r['rcn']}|{r['gunb']}"


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    raise TypeError(type(v))


def refresh_changes(conn=None, periods=PERIODS, segments=SEGMENTS) -> None:
    """Przelicza "Co się zmieniło" dla wszystkich okresów i typów działek i zapisuje w mart.changes_cache."""
    own = conn is None
    conn = conn or _conn()
    factory = conn.row_factory
    conn.row_factory = dict_row
    try:
        state = _changes_state(conn)
        data = _changes_all(conn, periods, segments)
        for (days, seg), d in data.items():
            conn.execute("""INSERT INTO mart.changes_cache (days, segment, state, data, computed_at)
                            VALUES (%s, %s, %s, %s, now())
                            ON CONFLICT (days, segment) DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data,
                            computed_at = now()""", (days, seg, state, json.dumps(d, default=_jsonable)))
        conn.commit()
    finally:
        conn.row_factory = factory
        if own:
            conn.close()


@app.get("/api/changes")
def changes(days: int = Query(7, ge=1, le=31), use: str | None = None):
    """Serie dzienne (ostatnie 60 dni) i tygodniowe oraz najważniejsze zmiany z ostatnich `days` dni.

    Gotowe odpowiedzi leżą w mart.changes_cache (przeliczane po porannym pobraniu); gdy stan danych
    się zmienił, przeliczamy raz wszystkie okresy i typy naraz. `use`: typ działek (domyślnie budowlane)."""
    seg = _segment(use)
    with _conn() as conn:
        if days not in PERIODS:
            return json.loads(json.dumps(_changes_all(conn, (days,), (seg,))[(days, seg)], default=_jsonable))
        state = _changes_state(conn)
        row = conn.execute("SELECT data FROM mart.changes_cache WHERE days = %s AND segment = %s AND state = %s",
                           (days, seg, state)).fetchone()
        if row:
            return row["data"]
    with _CHANGES_LOCK:   # kilka równoczesnych wejść: liczy tylko pierwsze
        with _conn() as conn:
            row = conn.execute("SELECT data FROM mart.changes_cache WHERE days = %s AND segment = %s AND state = %s",
                               (days, seg, _changes_state(conn))).fetchone()
            if row:
                return row["data"]
        refresh_changes()
    with _conn() as conn:
        return conn.execute("SELECT data FROM mart.changes_cache WHERE days = %s AND segment = %s",
                            (days, seg)).fetchone()["data"]


def _changes_all(conn, periods, segments=SEGMENTS) -> dict:
    """{(dni, typ działek): odpowiedź} dla wszystkich par."""
    empty = {"last_day": None, "daily": [], "weekly": [], "cuts": [], "fresh": [], "gone_fast": [], "gminy": [], "rcn": [], "permits": []}
    last = conn.execute(COMPLETE_DAY).fetchone()["d"]
    if last is None:
        return {(p, s): dict(empty) for p in periods for s in segments}
    out = {}
    with conn.transaction():
        for q in CHANGES_TEMP:
            conn.execute(q)
        permits = conn.execute("""
            SELECT date_trunc('month', decided_on)::date AS month, count(*) FILTER (WHERE single_family) AS houses
            FROM mart.gunb_permits WHERE decided_on >= DATE '2023-01-01'
            GROUP BY 1 ORDER BY 1""").fetchall()
        for seg in segments:
            _segment_views(conn, seg)
            for (days, _), v in _changes_segment(conn, last, periods, seg).items():
                out[(days, seg)] = {**v, "permits": permits, "segment": seg}
        conn.execute("DROP VIEW IF EXISTS ch_lst, ch_prop, ch_pday")
    return out


def _changes_segment(conn, last, periods, seg) -> dict:
    out = {}
    # liczniki per dzień, jedno przejście
    # aktywna w dniu D: któreś jej ogłoszenie było widziane przed D i po D (jednodniowa awaria portalu
    # nie "zdejmuje" jego działek); tylko pełne dni (<= last)
    rows = conn.execute("""
        WITH days AS (SELECT DISTINCT observed_at AS d FROM core.listing_observations
                      WHERE observed_at > %(last)s::date - 61 AND observed_at <= %(last)s)
        SELECT 'active' AS k, days.d, count(DISTINCT l.property_key)::float AS v
            FROM days JOIN ch_lst l ON l.fs <= days.d AND l.ls >= days.d GROUP BY days.d
        UNION ALL SELECT 'ppm2', d, percentile_cont(0.5) WITHIN GROUP (ORDER BY price / area)
                  FROM ch_pday WHERE d > %(last)s::date - 61 AND d <= %(last)s AND area > 0 GROUP BY d
        UNION ALL SELECT 'new', fs, count(*) FROM ch_prop WHERE genuine_new AND fs > %(last)s::date - 61
                  AND fs <= %(last)s GROUP BY fs
        UNION ALL SELECT 'gone_after', ls, count(*) FROM ch_prop WHERE gone_known AND ls > %(last)s::date - 62
                  AND ls < %(last)s GROUP BY ls
        UNION ALL SELECT 'cuts', d, count(*) FROM ch_pday WHERE d > %(last)s::date - 61 AND d <= %(last)s
                  AND price < prev_price * 0.995 GROUP BY d""", {"last": last}).fetchall()
    by: dict = {}
    for r in rows:
        by.setdefault(r["k"], {})[r["d"]] = r["v"]
    day_list = sorted(by.get("active", {}))
    daily = []
    for i, d in enumerate(day_list):
        prev = day_list[i - 1] if i else None
        daily.append({"d": d, "active": int(by["active"][d]), "new": int(by.get("new", {}).get(d, 0)),
                      # zniknięcie liczymy w dniu, w którym oferty już nie było
                      "gone": int(by.get("gone_after", {}).get(prev, 0)) if prev else 0,
                      "cuts": int(by.get("cuts", {}).get(d, 0)), "ppm2": by.get("ppm2", {}).get(d)})
    weekly: dict = {}
    for r in daily:
        wk = r["d"] - timedelta(days=r["d"].weekday())
        w = weekly.setdefault(wk, {"week": wk, "new": 0, "gone": 0, "cuts": 0, "active": 0, "ppm2": None})
        w["new"] += r["new"]
        w["gone"] += r["gone"]
        w["cuts"] += r["cuts"]
        w["active"], w["ppm2"] = r["active"], r["ppm2"]   # stan na ostatni dzień tygodnia
    rcn = conn.execute(f"""
        SELECT date_trunc('month', doc_date)::date AS month, count(*) AS tx,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2) AS ppm2
        FROM mart.rcn_land_transactions
        WHERE {_rcn_filter(seg)} AND ppm2 BETWEEN %(lo)s AND %(hi)s AND doc_date >= DATE '2024-01-01'
        GROUP BY 1 ORDER BY 1""", PPM2_RANGE).fetchall()
    for days in periods:
        params = {"last": last, "since": last - timedelta(days=days - 1)}
        cuts = conn.execute("""
            SELECT c.property_key AS id, c.gmina, c.teryt, c.price, c.area, round(c.price / c.area, 1) AS ppm2,
                   c.url, max(c.prev_price) AS before, round((c.price / max(c.prev_price) - 1) * 100, 1) AS change
            FROM ch_pday c WHERE c.d >= %(since)s AND c.price < c.prev_price * 0.995
              AND EXISTS (SELECT 1 FROM ch_pday n WHERE n.property_key = c.property_key AND n.d = %(last)s)
            GROUP BY 1, 2, 3, 4, 5, 7 ORDER BY change ASC LIMIT 8""", params).fetchall()
        fresh = conn.execute("""
            WITH med AS (SELECT teryt, percentile_cont(0.5) WITHIN GROUP (ORDER BY price / area) AS m
                         FROM ch_pday WHERE d = %(last)s GROUP BY 1 HAVING count(*) >= 5)
            SELECT pd.property_key AS id, pd.gmina, pd.teryt, pd.price, pd.area, round(pd.price / pd.area, 1) AS ppm2,
                   pd.url, round(((pd.price / pd.area / med.m::numeric - 1) * 100)::numeric, 0) AS vs_median
            FROM ch_prop p JOIN ch_pday pd ON pd.property_key = p.property_key AND pd.d = %(last)s
            JOIN med ON med.teryt = pd.teryt
            WHERE p.genuine_new AND p.fs >= %(since)s
            ORDER BY pd.price / pd.area / med.m ASC LIMIT 8""", params).fetchall()
        gone_fast = conn.execute("""
            SELECT pd.property_key AS id, pd.gmina, pd.teryt, pd.price, pd.area, round(pd.price / pd.area, 1) AS ppm2,
                   pd.url, p.ls - p.fs AS days_listed
            FROM ch_prop p JOIN ch_pday pd ON pd.property_key = p.property_key AND pd.d = p.ls
            WHERE p.gone_known AND p.ls >= %(since)s::date - 1 AND p.ls < %(last)s AND p.genuine_new
            ORDER BY p.ls - p.fs ASC, pd.price / pd.area ASC LIMIT 8""", params).fetchall()
        gminy = conn.execute("""
            SELECT pd.teryt, max(pd.gmina) AS gmina,
                   count(DISTINCT pd.property_key) FILTER (WHERE p.genuine_new AND p.fs >= %(since)s) AS new,
                   count(DISTINCT pd.property_key) FILTER (WHERE p.gone_known AND p.ls < %(last)s
                                                          AND p.ls >= %(since)s::date - 1 AND pd.d = p.ls) AS gone,
                   count(DISTINCT pd.property_key) FILTER (WHERE pd.d >= %(since)s
                                                          AND pd.price < pd.prev_price * 0.995) AS cuts,
                   count(DISTINCT pd.property_key) FILTER (WHERE pd.d = %(last)s) AS active
            FROM ch_pday pd JOIN ch_prop p USING (property_key)
            WHERE pd.d >= %(since)s::date - 1 OR pd.d = p.ls
            GROUP BY pd.teryt
            HAVING count(DISTINCT pd.property_key) FILTER (WHERE p.genuine_new AND p.fs >= %(since)s)
                 + count(DISTINCT pd.property_key) FILTER (WHERE pd.d >= %(since)s
                                                          AND pd.price < pd.prev_price * 0.995) > 0
            ORDER BY 3 + 4 + 5 DESC LIMIT 10""", params).fetchall()
        out[(days, seg)] = {"last_day": last, "since": params["since"], "daily": daily,
                            "weekly": list(weekly.values()), "cuts": cuts, "fresh": fresh, "gone_fast": gone_fast,
                            "gminy": gminy, "rcn": rcn}
    return out


def warm_up() -> None:
    """Po starcie strony: przelicz "Co się zmieniło", jeśli zapisane wyniki są nieaktualne (w tle)."""
    try:
        with _conn() as conn:
            fresh = conn.execute("SELECT count(*) AS n FROM mart.changes_cache WHERE state = %s",
                                 (_changes_state(conn),)).fetchone()["n"]
        if fresh < len(PERIODS) * len(SEGMENTS):
            with _CHANGES_LOCK:
                refresh_changes()
    except Exception:  # noqa: BLE001 - brak bazy przy starcie nie może zatrzymać strony
        pass


@app.on_event("startup")
def _startup_warm_up() -> None:
    if os.environ.get("LMI_WARM_UP", "1") != "0":
        threading.Thread(target=warm_up, daemon=True).start()


# zł/m² poza tym zakresem to zwykle drogi, udziały albo błędy w rejestrze
PPM2_RANGE = {"lo": 5, "hi": 5000}


@app.get("/api/municipality/{teryt}/transactions")
def municipality_transactions(teryt: str, limit: int = Query(50, ge=1, le=500)):
    """Ceny transakcyjne gruntów z RCN: podsumowanie 12 miesięcy, kwartały i ostatnie akty."""
    _check_teryt(teryt)
    p = {"t": teryt, "limit": limit, **PPM2_RANGE}
    summary = _rows("""
        -- okno 12 miesięcy od ostatniego aktu w powiecie tej gminy (starostwa przekazują dane z różnym opóźnieniem)
        WITH last AS (SELECT max(doc_date) AS d FROM scrape.rcn_parcels WHERE left(parcel_id, 4) = left(%(t)s, 4))
        SELECT (SELECT d FROM last) AS data_until,
               count(*) FILTER (WHERE doc_date > (SELECT d FROM last) - 365)            AS tx_12m,
               count(*) FILTER (WHERE buildable AND doc_date > (SELECT d FROM last) - 365) AS tx_build_12m,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2)
                   FILTER (WHERE buildable AND doc_date > (SELECT d FROM last) - 365)     AS ppm2_build_12m,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2)
                   FILTER (WHERE doc_date > (SELECT d FROM last) - 365)                  AS ppm2_12m
        FROM mart.rcn_land_transactions
        WHERE gmina_teryt = %(t)s AND ppm2 BETWEEN %(lo)s AND %(hi)s""", p)[0]
    quarters = _rows("""
        SELECT date_trunc('quarter', doc_date)::date AS quarter, count(*) AS tx,
               count(*) FILTER (WHERE buildable) AS tx_build,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2) FILTER (WHERE buildable) AS ppm2_build
        FROM mart.rcn_land_transactions
        WHERE gmina_teryt = %(t)s AND ppm2 BETWEEN %(lo)s AND %(hi)s
        GROUP BY 1 ORDER BY 1""", p)
    recent = _rows("""
        SELECT doc_date, price, area_m2 AS area, ppm2, parcels, mpzp, land_use, buildable, tender, market,
               seller_type, buyer_type, locality, parcel_ids
        FROM mart.rcn_land_transactions
        WHERE gmina_teryt = %(t)s AND ppm2 BETWEEN %(lo)s AND %(hi)s
        ORDER BY doc_date DESC NULLS LAST, tx_id LIMIT %(limit)s""", p)
    return {"summary": summary, "quarters": quarters, "recent": recent}


@app.get("/api/municipality/{teryt}/weekly")
def municipality_weekly(teryt: str, use: str | None = None):
    _check_teryt(teryt)
    seg = _segment(use)
    rows = _rows("""
        SELECT week_start, active_supply AS supply, new_listings AS new, disappeared_listings AS gone,
               median_price_per_m2 AS ppm2, absorption_rate AS absorption,
               discounted_share AS discounted, median_days_to_disappear AS days
        FROM mart.weekly_region_metrics WHERE municipality_teryt = %(t)s AND segment = %(s)s
        ORDER BY week_start""", {"t": teryt, "s": seg})
    if not rows:
        raise HTTPException(404, "Brak danych dla tej gminy")
    # punkt odniesienia: mediana z gmin z wystarczającą liczbą ofert, tydzień po tygodniu
    benchmark = _rows("""
        SELECT week_start,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY median_price_per_m2) AS ppm2,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY absorption_rate) AS absorption,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY discounted_share) AS discounted,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY active_supply) AS supply
        FROM mart.weekly_region_metrics WHERE active_supply >= %(m)s AND segment = %(s)s
        GROUP BY week_start ORDER BY week_start""", {"m": MIN_SUPPLY_FOR_RANK, "s": seg})
    return {"weeks": rows, "benchmark": benchmark}


SORTS = {
    "ppm2": "ppm2 ASC",
    "price": "price ASC",
    "area": "area DESC",
    "newest": "start_date DESC",
    "longest": "start_date ASC",
    "cut": "price_change ASC",
    "pushed": "pushed_up_at DESC NULLS LAST",
    "saved": "saved DESC NULLS LAST",
    "views": "views DESC NULLS LAST",
    "views_rate": "views_per_day DESC NULLS LAST",
}


@app.get("/api/municipality/{teryt}/offers")
def municipality_offers(
    request: Request,
    teryt: str,
    land_use: str | None = None,
    min_area: float | None = Query(None, ge=0),
    max_area: float | None = Query(None, ge=0),
    max_ppm2: float | None = Query(None, ge=0),
    min_age_days: int | None = Query(None, ge=0),
    seller: str | None = Query(None, pattern="^(prywatny|biuro|deweloper)$"),
    media: str | None = Query(None, pattern="^(prąd|woda|gaz|kanalizacja|prąd\\+woda)$"),
    sort: str = "ppm2",
    limit: int = Query(300, ge=1, le=1000),
):
    _check_teryt(teryt)
    if sort not in SORTS:
        raise HTTPException(400, f"sort: jedno z {', '.join(SORTS)}")
    where = ["active"]
    params: dict = {"t": teryt, "limit": limit}
    if land_use:
        where.append("land_use = %(use)s")
        params["use"] = land_use
    if min_area is not None:
        where.append("area >= %(min_area)s")
        params["min_area"] = min_area
    if max_area is not None:
        where.append("area <= %(max_area)s")
        params["max_area"] = max_area
    if max_ppm2 is not None:
        where.append("ppm2 <= %(max_ppm2)s")
        params["max_ppm2"] = max_ppm2
    if min_age_days is not None:
        where.append("age_days >= %(min_age)s")
        params["min_age"] = min_age_days
    if seller:
        # jak merge_features: właściciel potwierdzony przez Adresowo/Gratkę albo "prywatny" bez biura na innym portalu
        has = ("(features_raw @> jsonb_build_array(jsonb_build_object('seller', {v}::text)) "
               "OR features_raw @> jsonb_build_array(jsonb_build_object('list_seller', {v}::text)))")
        agency = f"({has.format(v=chr(39) + 'biuro' + chr(39))} OR {has.format(v=chr(39) + 'deweloper' + chr(39))})"
        owner = " OR ".join(f"features_raw @> jsonb_build_array(jsonb_build_object('src', '{src}', 'seller', 'prywatny'))"
                            for src in OWNER_CONFIRMED)
        if seller == "prywatny":
            where.append(f"(({owner}) OR ({has.format(v='%(seller)s')} AND NOT {agency}))")
        else:
            where.append(f"({has.format(v='%(seller)s')} AND NOT ({owner}))")
        params["seller"] = seller
    for i, m in enumerate((media or "").split("+") if media else []):
        where.append(f"features_raw @> jsonb_build_array(jsonb_build_object('media', jsonb_build_array(%(m{i})s::text)))")
        params[f"m{i}"] = m
    params["me"] = _user(request)
    return _offers("o.municipality_teryt = %(t)s", where, params, sort)



def _offers(scope: str, where: list[str], params: dict, sort: str) -> list[dict]:
    """Działki (po deduplikacji) z ogłoszeń spełniających `scope` (warunek SQL na obserwacjach `o`)."""
    rows = _rows(f"""
        WITH links AS (
            SELECT source_id, source_listing_id, property_key FROM core.listing_property_links
            WHERE run_id = (SELECT max(run_id) FROM core.dedup_runs)
        ),
        -- aktywna = widziana w ostatnim pobraniu swojego źródła
        src_last AS (
            SELECT source_id, max(observed_at) AS d FROM core.listing_observations GROUP BY source_id
        ),
        o AS (
            SELECT o.*, l.property_key, o.observed_at = sl.d AS in_latest
            FROM core.listing_observations o
            JOIN links l USING (source_id, source_listing_id)
            JOIN src_last sl USING (source_id)
            WHERE {scope}
        ),
        p AS (
            SELECT property_key,
                   min(observed_at) AS first_seen, max(observed_at) AS last_seen,
                   count(DISTINCT source_id) AS portals,
                   (array_agg(price_pln ORDER BY observed_at))[1]       AS first_price,
                   (array_agg(price_pln ORDER BY observed_at DESC))[1]  AS price_obs,
                   (array_agg(area_m2 ORDER BY observed_at DESC))[1]    AS area,
                   (array_agg(land_use ORDER BY observed_at DESC))[1]   AS land_use,
                   (array_agg(url ORDER BY observed_at DESC))[1]        AS url_obs,
                   bool_or(lat IS NOT NULL)                             AS precise,
                   bool_or(in_latest)                                   AS active,
                   min(listed_at)                                       AS listed_at,
                   max(pushed_up_at)                                    AS pushed_up_at,
                   (array_agg(source_listing_id ORDER BY observed_at DESC)
                        FILTER (WHERE source_id = 'otodom'))[1]          AS otodom_id,
                   (array_agg(source_listing_id ORDER BY observed_at DESC)
                        FILTER (WHERE source_id = 'gratka'))[1]          AS gratka_id,
                   (array_agg(source_id ORDER BY observed_at DESC, source_id))[1]          AS source_obs,
                   (array_agg(source_listing_id ORDER BY observed_at DESC, source_id))[1]  AS source_listing_id_obs,
                   array_agg(DISTINCT source_id)                         AS sources,
                   array_agg(DISTINCT source_id || ':' || source_listing_id) AS listing_keys,
                   (array_agg(municipality_name ORDER BY observed_at DESC))[1] AS municipality,
                   (array_agg(municipality_teryt ORDER BY observed_at DESC))[1] AS teryt
            FROM o GROUP BY property_key
        ),
        -- poszczególne ogłoszenia działki: aktywne? ostatnia cena, link, data ostatniej aktualizacji w portalu
        lst AS (
            SELECT o.source_id, o.source_listing_id, o.property_key, bool_or(o.in_latest) AS active,
                   (array_agg(o.price_pln ORDER BY o.observed_at DESC))[1] AS last_price,
                   (array_agg(o.url ORDER BY o.observed_at DESC))[1] AS url,
                   max(o.observed_at) AS last_seen,
                   greatest(max(o.pushed_up_at), min(o.listed_at),
                            max((coalesce(od.detail, pd.detail)->'features'->>'updated_at')::date)) AS refreshed
            FROM o
            LEFT JOIN scrape.otodom_details od ON o.source_id = 'otodom' AND od.ad_id = o.source_listing_id
            LEFT JOIN scrape.portal_details pd ON pd.source_id = o.source_id AND pd.ad_id = o.source_listing_id
            GROUP BY 1, 2, 3
        ),
        -- link do ogłoszenia najświeższego (aktywne, ostatnio aktualizowane/podbite/wystawione); cena: najniższa aktywna
        rep AS (
            SELECT DISTINCT ON (property_key) property_key, source_id AS rep_source, source_listing_id AS rep_id,
                   url AS rep_url
            FROM lst ORDER BY property_key, active DESC, refreshed DESC NULLS LAST, last_seen DESC, source_id
        ),
        offs AS (
            SELECT property_key, min(last_price) FILTER (WHERE active) AS min_active_price,
                   json_agg(json_build_object('source', source_id, 'url', url, 'price', last_price, 'active', active,
                                              'refreshed', refreshed)
                            ORDER BY active DESC, refreshed DESC NULLS LAST, last_price) AS offers
            FROM lst GROUP BY 1
        ),
        p2 AS (
            SELECT p.*, coalesce(offs.min_active_price, p.price_obs) AS price, offs.offers,
                   coalesce(rep.rep_url, p.url_obs) AS url, coalesce(rep.rep_source, p.source_obs) AS source,
                   coalesce(rep.rep_id, p.source_listing_id_obs) AS source_listing_id
            FROM p LEFT JOIN rep USING (property_key) LEFT JOIN offs USING (property_key)
        ),
        -- historia ceny: dni, w których cena (najniższa z portali) się zmieniła
        daily AS (
            SELECT property_key, observed_at, min(price_pln) AS price FROM o GROUP BY 1, 2
        ),
        changes AS (
            SELECT property_key,
                   json_agg(json_build_object('date', observed_at, 'price', price) ORDER BY observed_at) AS history
            FROM (SELECT *, lag(price) OVER (PARTITION BY property_key ORDER BY observed_at) AS prev FROM daily) d
            WHERE prev IS NULL OR price <> prev
            GROUP BY property_key
        ),
        -- historia z konta Otodom (scrape.otodom_details), jeśli została pobrana
        oh AS (
            SELECT p.property_key, d.detail->'history' AS otodom_history,
                   d.detail->>'land_use_source' AS land_use_source,
                   (d.detail->'stats'->>'views')::int AS views, (d.detail->'stats'->>'saved')::int AS saved,
                   d.detail->'views_log' AS views_log,
                   (SELECT (e->>'price')::numeric FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->>'price' IS NOT NULL ORDER BY e->>'date' LIMIT 1) AS hist_first_price,
                   (SELECT (e->>'date')::date FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->'changes' ? 'FIRST_PUBLISHED' ORDER BY e->>'date' LIMIT 1) AS hist_published,
                   (SELECT count(*) FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->'changes' ? 'ACTIVATED')::int AS relists
            FROM p JOIN scrape.otodom_details d ON d.ad_id = p.otodom_id
        ),
        -- liczba odsłon z Gratki (gdy oferty nie ma na Otodomie albo brak tam statystyk)
        gv AS (
            SELECT p.property_key, (g.detail->'stats'->>'views')::int AS views, g.detail->'views_log' AS views_log
            FROM p JOIN scrape.portal_details g ON g.source_id = 'gratka' AND g.ad_id = p.gratka_id
        ),
        f AS (
            SELECT p.*, c.history, oh.otodom_history,
                   coalesce(oh.views, gv.views) AS views,
                   CASE WHEN oh.views IS NOT NULL THEN 'otodom' WHEN gv.views IS NOT NULL THEN 'gratka' END
                        AS views_source,
                   CASE WHEN oh.views IS NOT NULL THEN oh.views_log ELSE gv.views_log END AS views_log,
                   oh.saved, coalesce(oh.relists, 0) AS relists,
                   coalesce(oh.land_use_source, pd.detail->>'land_use_source') AS land_use_source,
                   round(price / area, 1) AS ppm2,
                   -- zmiana ceny od pierwszej znanej: z historii Otodom, a bez niej od pierwszej obserwacji
                   round((price / coalesce(oh.hist_first_price, first_price) - 1) * 100, 1) AS price_change,
                   least(first_seen, coalesce(listed_at, oh.hist_published, first_seen)) AS start_date,
                   last_seen - least(first_seen, coalesce(listed_at, oh.hist_published, first_seen)) AS age_days
            FROM p2 p LEFT JOIN changes c USING (property_key) LEFT JOIN oh USING (property_key)
                   LEFT JOIN gv USING (property_key)
                   LEFT JOIN scrape.portal_details pd
                          ON pd.source_id = p.source AND pd.ad_id = p.source_listing_id
        )
        SELECT property_key AS id, price, area, ppm2, land_use, url, portals, precise, source, sources,
               first_seen, listed_at, pushed_up_at, start_date, age_days, price_change, history,
               otodom_history, views, views_source, views_per_day, saved, relists, land_use_source,
               active, municipality, teryt, listing_keys, features_raw, offers,
               -- zespół: ulubione (moje / ile osób, kto) i liczba komentarzy do tej działki
               EXISTS (SELECT 1 FROM app.favorites fv WHERE fv.user_email = %(me)s
                         AND fv.source_id || ':' || fv.source_listing_id = ANY(listing_keys)) AS fav,
               (SELECT array_agg(DISTINCT fv.user_email ORDER BY fv.user_email) FROM app.favorites fv
                 WHERE fv.source_id || ':' || fv.source_listing_id = ANY(listing_keys)) AS fav_users,
               (SELECT count(*) FROM app.comments c WHERE c.deleted_at IS NULL
                 AND c.source_id || ':' || c.source_listing_id = ANY(listing_keys))::int AS comments
        FROM (SELECT *, scrape.views_per_day(views_log, start_date) AS views_per_day,
                     -- parametry ze wszystkich portali, na których jest ta działka (media, dojazd, sprzedający...)
                     (SELECT coalesce(jsonb_agg(x.f || jsonb_build_object('src', x.src)), '[]'::jsonb) FROM (
                         SELECT 'otodom' AS src, coalesce(d.detail->'features', '{{}}') || jsonb_strip_nulls(jsonb_build_object(
                                    'list_seller', d.detail->'list_seller')) AS f
                         FROM unnest(listing_keys) k JOIN scrape.otodom_details d
                           ON split_part(k, ':', 1) = 'otodom' AND d.ad_id = substr(k, 8)
                         WHERE d.detail ? 'features' OR d.detail ? 'list_seller'
                         UNION ALL
                         SELECT pd.source_id, pd.detail->'features'
                         FROM unnest(listing_keys) k JOIN scrape.portal_details pd
                           ON pd.source_id = split_part(k, ':', 1) AND pd.ad_id = substr(k, strpos(k, ':') + 1)
                         WHERE pd.detail ? 'features') x) AS features_raw
              FROM f) f WHERE {' AND '.join(where)}
        ORDER BY {SORTS[sort]}, property_key
        LIMIT %(limit)s""", params)
    for r in rows:
        r["features"] = merge_features(r.pop("features_raw") or [])
    return rows


# portale, na których "prywatny" to jawne oznaczenie właściciela (Adresowo: "Oferta bezpośrednio od właściciela",
# Gratka: osoba prywatna). Na Otodomie z kont prywatnych wystawiają też biura i deweloperzy.
OWNER_CONFIRMED = ("adresowo", "gratka")


def merge_features(parts: list[dict]) -> dict:
    """Jedna działka, kilka portali: suma mediów i dróg. Sprzedający: "prywatny", gdy właściciela potwierdza
    Adresowo/Gratka (często ta sama działka jest też u biura: do właściciela da się dotrzeć bezpośrednio);
    inaczej biuro/deweloper, jeśli którykolwiek portal tak pokazuje; inaczej "prywatny" z Otodomu."""
    out = {"seller": None, "negotiable": None, "media": [], "access": [], "fence": None, "vicinity": [],
           "updated_at": None, "params": {}}
    for f in parts:
        if not isinstance(f, dict):
            continue
        rank = {None: 0, "prywatny": 1, "biuro": 2, "deweloper": 3, "właściciel": 4}
        for seller in (f.get("seller"), f.get("list_seller")):
            if seller == "prywatny" and f.get("src") in OWNER_CONFIRMED:
                seller = "właściciel"
            if rank.get(seller, 0) > rank.get(out["seller"], 0):
                out["seller"] = seller
        for k in ("media", "access", "vicinity"):
            out[k] = sorted(set(out[k]) | set(f.get(k) or []))
        for k in ("negotiable", "fence"):
            if f.get(k) is not None:
                out[k] = bool(out[k]) or f[k]
        if f.get("updated_at") and (out["updated_at"] is None or f["updated_at"] > out["updated_at"]):
            out["updated_at"] = f["updated_at"]
        if f.get("params"):
            out["params"][f.get("src") or "portal"] = f["params"]
    if out["seller"] == "właściciel":
        out["seller"] = "prywatny"
    return out


# --- status systemu (administrator) --------------------------------------------------------------

QUALITY_JUMP = 1.25     # wzrost liczby podejrzanych grup / błędnych ogłoszeń, od którego jest powiadomienie
STALE_MINUTES = 30      # zadanie "running" bez znaku życia dłużej = pewnie przerwane
STATUS_TEXT = {"ok": "OK", "warning": "z ostrzeżeniem", "error": "błąd", "blocked": "blokada portalu (403)",
               "layout_changed": "portal zmienił wygląd strony", "running": "trwa"}


@app.get("/api/admin/status")
def admin_status(request: Request):
    """Wszystko, co admin powinien wiedzieć: co trwa, co nie przeszło, kompletność RCN, stan pamięci ofert."""
    _require_admin(request)
    jobs = _rows("""SELECT job, state, started_at, updated_at, finished_at, message,
                           state = 'running' AND updated_at < now() - make_interval(mins => %(m)s) AS stale
                    FROM scrape.job_status ORDER BY job""", {"m": STALE_MINUTES})
    sources = _rows("""
        SELECT s.source_id AS source, s.name,
               (SELECT finished_at FROM scrape.runs r WHERE r.source_id = s.source_id AND r.status IN ('ok', 'warning')
                 ORDER BY run_id DESC LIMIT 1) AS last_ok,
               (SELECT row_to_json(x) FROM (SELECT started_at, finished_at, status, rows_written, message
                   FROM scrape.runs r WHERE r.source_id = s.source_id ORDER BY run_id DESC LIMIT 1) x) AS latest,
               (SELECT count(*) FROM scrape.portal_details d WHERE d.source_id = s.source_id)
                 + CASE WHEN s.source_id = 'otodom' THEN (SELECT count(*) FROM scrape.otodom_details) ELSE 0 END
                 AS cached_offers
        FROM core.sources s WHERE s.approved ORDER BY s.source_id""")
    runs = _rows("""SELECT run_id, source_id AS source, started_at, finished_at, status, rows_written, message
                    FROM scrape.runs ORDER BY run_id DESC LIMIT 20""")
    rcn = _rows("""SELECT count(*) AS rows, min(doc_date) AS since, max(doc_date) AS until,
                          (SELECT count(*) FROM mart.rcn_land_transactions) AS land_tx,
                          (SELECT max(fetched_at) FROM scrape.rcn_fetch_log) AS last_fetch,
                          (SELECT coalesce(json_agg(gaps), '[]') FROM (
                              SELECT DISTINCT ON (teryt_prefix, period_start) gaps FROM scrape.rcn_fetch_log
                              ORDER BY teryt_prefix, period_start, fetched_at DESC) l WHERE gaps IS NOT NULL) AS gaps
                   FROM scrape.rcn_parcels""")[0]
    feedback_open = _rows("SELECT count(*) AS n FROM app.feedback WHERE status = 'nowe'")[0]["n"]

    issues = []
    names = {x["source"]: x["name"] for x in sources}
    running = {j["job"] for j in jobs if j["state"] == "running" and not j["stale"]}
    for x in sources:
        lt = x["latest"]
        if lt and lt["status"] not in ("ok", "warning"):
            again = x["source"] in running
            issues.append({"level": "warn" if again else "bad",
                           "title": f"{x['name']}: ostatnie pobieranie nie przeszło"
                                    + (" (trwa ponowne)" if again else ""),
                           "detail": f"{STATUS_TEXT.get(lt['status'], lt['status'])}"
                                     + (f": {lt['message']}" if lt.get("message") else ""),
                           "when": lt["started_at"]})
        elif lt and lt["status"] == "warning" and lt.get("message"):
            issues.append({"level": "warn", "title": f"{x['name']}: ostrzeżenie", "detail": lt["message"],
                           "when": lt["started_at"]})
    for x in sources:
        if x["last_ok"] is not None:
            stale = _rows("SELECT %(t)s::timestamptz < now() - interval '26 hours' AS old", {"t": x["last_ok"]})[0]["old"]
            if stale:
                issues.append({"level": "warn", "title": f"{x['name']}: brak udanego pobrania od ponad doby",
                               "detail": "ostatnie udane", "when": x["last_ok"]})
    for j in jobs:
        label = names.get(j["job"], "RCN (ceny transakcyjne)" if j["job"] == "rcn" else j["job"])
        if j["stale"]:
            issues.append({"level": "warn", "title": f"{label}: zadanie nie daje znaku życia",
                           "detail": f"ostatni komunikat: {j['message'] or '–'}", "when": j["updated_at"]})
        elif j["state"] == "error" and j["job"] == "rcn":
            issues.append({"level": "bad", "title": f"{label}: zadanie przerwane błędem",
                           "detail": j["message"] or "", "when": j["finished_at"] or j["updated_at"]})
    # zapytanie o akty bez daty geoportal odrzuca zawsze (403 po jego stronie): to nie luka w danych
    gaps = [g for g in rcn["gaps"] if not g.startswith("akty bez daty")]
    if gaps:
        issues.append({"level": "info", "title": f"RCN: luki w usłudze geoportalu ({len(gaps)})",
                       "detail": "; ".join(gaps[:5]), "when": rcn["last_fetch"]})
    if feedback_open:
        issues.append({"level": "info", "title": f"Nowe zgłoszenia od zespołu: {feedback_open}",
                       "detail": "przycisk „Zgłoszenia”", "when": None})
    last2 = _rows("""SELECT run_id, created_at AS run_at, algorithm_version, report FROM core.dedup_runs
                     ORDER BY run_id DESC LIMIT 2""")
    quality = last2[0] if last2 else None
    rep = (quality or {}).get("report") or {}
    prev = (last2[1].get("report") or {}) if len(last2) > 1 else {}

    def jumped(k):
        # stały poziom widać w "Jakość danych"; powiadomienie tylko przy wyraźnym skoku względem poprzedniego przebiegu
        return bool(rep.get(k)) and prev.get(k) is not None and rep[k] > prev[k] * QUALITY_JUMP + 10

    if jumped("suspicious"):
        issues.append({"level": "info", "title": f"Deduplikacja: {rep['suspicious']} grup do sprawdzenia",
                       "detail": "połączone ogłoszenia z dużą różnicą ceny lub metrażu (sekcja Jakość danych)",
                       "when": quality["run_at"]})
    if jumped("outliers"):
        issues.append({"level": "info", "title": f"Nieprawdopodobne ceny/metraże: {rep['outliers']} ogłoszeń",
                       "detail": "np. cena za m² poniżej 2 zł albo metraż poniżej 100 m² (sekcja Jakość danych)",
                       "when": quality["run_at"]})
    return {"issues": issues, "jobs": jobs, "sources": sources, "runs": runs, "rcn": rcn, "quality": quality,
            "problems": sum(1 for i in issues if i["level"] in ("bad", "warn"))}


# --- zgłoszenia błędów i poprawek ----------------------------------------------------------------

FEEDBACK_KINDS = ("błąd", "poprawka danych", "pomysł")


@app.post("/api/feedback")
def feedback_add(request: Request, kind: str = Body(...), body: str = Body(...), context: dict = Body({})):
    body = body.strip()
    if kind not in FEEDBACK_KINDS:
        raise HTTPException(400, f"rodzaj: jeden z {', '.join(FEEDBACK_KINDS)}")
    if not 3 <= len(body) <= 4000:
        raise HTTPException(400, "opis: od 3 do 4000 znaków")
    # kontekst tylko z dozwolonych, krótkich pól (bez dowolnych danych z przeglądarki)
    # klucze – ogłoszenia zgłoszonej oferty (źródło:numer): po nich panel zgłoszeń znajduje ją także po zmianie grupowania
    ctx = {k: str(v)[:1500 if k in ("obszary", "ogloszenia", "klucze") else 300] for k, v in (context or {}).items()
           if k in ("gmina", "teryt", "widok", "adres", "przegladarka", "ekran", "oferta", "obszary",
                    "problem", "dzialka", "ogloszenia", "klucze")
           and v not in (None, "")}
    import json as _json
    with _conn() as conn:
        row = conn.execute("""INSERT INTO app.feedback (user_email, kind, body, context) VALUES (%s, %s, %s, %s)
                              RETURNING feedback_id AS id""", (_user(request), kind, body, _json.dumps(ctx))).fetchone()
    return row


def feedback_rows(status: str | None = "nowe") -> list[dict]:
    return _rows("""SELECT feedback_id AS id, created_at, user_email AS author, kind, body, context, status
                    FROM app.feedback WHERE %(s)s::text IS NULL OR status = %(s)s
                    ORDER BY created_at""", {"s": status})


def feedback_text(rows: list[dict]) -> str:
    """Zgłoszenia jako zwykły tekst do skopiowania (np. do rozmowy z Claude)."""
    if not rows:
        return "Brak zgłoszeń."
    out = [f"Zgłoszenia z Radaru Działek ({len(rows)}):", ""]
    for r in rows:
        c = dict(r["context"] or {})
        areas = c.pop("obszary", None)
        links = c.pop("ogloszenia", None)
        problem = c.pop("problem", None)
        c.pop("przegladarka", None)
        ctx = ", ".join(f"{k}: {v}" for k, v in c.items())
        when = r["created_at"].strftime("%Y-%m-%d %H:%M") if hasattr(r["created_at"], "strftime") else r["created_at"]
        out.append(f"#{r['id']} [{r['kind']}] {when} · {r['author']}" + (f" · {r['status']}" if r["status"] != "nowe" else ""))
        if problem:
            out.append(f"Problem z ofertą: {problem}")
        out.append(r["body"])
        if links:
            out.extend(f"  ogłoszenie: {u.strip()}" for u in links.split(" | "))
        if areas:
            out.extend(f"  - {a.strip()}" for a in areas.split(" | "))
        if ctx:
            out.append(f"(gdzie: {ctx})")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


@app.get("/api/feedback")
def feedback_list(request: Request, status: str = "nowe"):
    _require_admin(request)
    return feedback_rows(None if status == "wszystkie" else status)


@app.get("/api/feedback/export", response_class=PlainTextResponse)
def feedback_export(request: Request, status: str = "nowe"):
    _require_admin(request)
    return feedback_text(feedback_rows(None if status == "wszystkie" else status))


def _zgloszone_klucze(context: dict) -> list[str]:
    """ogłoszenia zgłoszonej oferty: klucze źródło:numer (zgłoszenia od 25.10) albo – w starszych – po adresach URL"""
    if context.get("klucze"):
        return [k for k in context["klucze"].split(",") if ":" in k][:30]
    urls = [u.strip() for u in (context.get("ogloszenia") or "").split(" | ") if u.strip()][:30]
    if not urls:
        return []
    return [r["k"] for r in _rows("""SELECT DISTINCT source_id || ':' || source_listing_id AS k
                                     FROM core.listing_observations WHERE url = ANY(%(u)s)""", {"u": urls})]


@app.get("/api/feedback/{feedback_id}/offers")
def feedback_offers(request: Request, feedback_id: int):
    """Zgłoszona oferta dziś (25.10, prośba użytkownika: zgłoszenie ma prowadzić dokładnie do miejsca i pokazać, czy poprawka
    zadziałała): działki według bieżącej deduplikacji, w których są ogłoszenia ze zgłoszenia – także nieaktywne."""
    _require_admin(request)
    found = _rows("SELECT context FROM app.feedback WHERE feedback_id = %(i)s", {"i": feedback_id})
    if not found:
        raise HTTPException(404, "nie ma takiego zgłoszenia")
    keys = _zgloszone_klucze(found[0]["context"] or {})
    if not keys:
        return {"klucze": [], "oferty": []}
    scope = """l.property_key IN (SELECT l2.property_key FROM links l2
                                  WHERE l2.source_id || ':' || l2.source_listing_id = ANY(%(keys)s))"""
    return {"klucze": keys,
            "oferty": _offers(scope, ["true"], {"me": _user(request), "limit": 50, "keys": keys}, "newest")}


@app.get("/api/municipality/{teryt}/permits")
def municipality_permits(teryt: str):
    """Pozwolenia na budowę (GUNB) w gminie: kwartały (domy jednorodzinne i wszystkie) i podsumowanie 12 miesięcy."""
    _check_teryt(teryt)
    quarters = _rows("""
        SELECT date_trunc('quarter', decided_on)::date AS quarter, count(*) FILTER (WHERE single_family) AS houses,
               count(*) AS total
        FROM mart.gunb_permits WHERE gmina_teryt = %(t)s AND decided_on >= DATE '2019-01-01'
        GROUP BY 1 ORDER BY 1""", {"t": teryt})
    summary = _rows("""
        WITH x AS (SELECT max(decided_on) AS m FROM mart.gunb_permits)
        SELECT (SELECT m FROM x) AS data_until,
               count(*) FILTER (WHERE single_family AND decided_on > (SELECT m FROM x) - 365) AS houses_12m,
               count(*) FILTER (WHERE single_family AND decided_on > (SELECT m FROM x) - 730
                                AND decided_on <= (SELECT m FROM x) - 365) AS houses_prev_12m,
               count(*) FILTER (WHERE decided_on > (SELECT m FROM x) - 365) AS total_12m
        FROM mart.gunb_permits WHERE gmina_teryt = %(t)s""", {"t": teryt})[0]
    return {"summary": summary, "quarters": quarters}


# --- nowości dla zespołu ------------------------------------------------------------------------------

def business_days_after(start: date, days: int = 4) -> date:
    """Ostatni dzień widoczności: `days` dni roboczych (pn–pt) licząc dzień publikacji, jeśli roboczy."""
    d, left = start, days
    while True:
        if d.weekday() < 5:
            left -= 1
            if left == 0:
                return d
        d += timedelta(days=1)


def add_announcement(conn, title: str, body: str, author: str, days: int = 4, today: date | None = None) -> dict:
    title, body = title.strip(), (body or "").strip()
    if not 3 <= len(title) <= 140 or len(body) > 1500:
        raise ValueError("tytuł 3–140 znaków, treść do 1500")
    until = business_days_after(today or date.today(), max(1, min(days, 30)))
    return conn.execute("""INSERT INTO app.announcements (title, body, created_by, visible_until)
                           VALUES (%s, %s, %s, %s) RETURNING announcement_id AS id, visible_until""",
                        (title, body, author, until)).fetchone()


@app.get("/api/announcements")
def announcements():
    return _rows("""SELECT announcement_id AS id, title, body, created_at, visible_until
                    FROM app.announcements WHERE removed_at IS NULL AND visible_until >= current_date
                    ORDER BY created_at DESC LIMIT 10""")


@app.post("/api/announcements")
def announcement_add(request: Request, title: str = Body(...), body: str = Body(""), days: int = Body(4)):
    _require_admin(request)
    with _conn() as conn:
        try:
            return add_announcement(conn, title, body, _user(request), days)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@app.delete("/api/announcements/{announcement_id}")
def announcement_remove(request: Request, announcement_id: int):
    _require_admin(request)
    with _conn() as conn:
        cur = conn.execute("UPDATE app.announcements SET removed_at = now() WHERE announcement_id = %s AND removed_at IS NULL",
                           (announcement_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "nie ma takiej nowości")
    return {"ok": True}


@app.post("/api/feedback/{feedback_id}/status")
def feedback_status(request: Request, feedback_id: int, status: str = Body(..., embed=True)):
    _require_admin(request)
    if status not in ("nowe", "zrobione"):
        raise HTTPException(400, "status: nowe albo zrobione")
    with _conn() as conn:
        cur = conn.execute("""UPDATE app.feedback SET status = %s,
                              resolved_at = CASE WHEN %s = 'zrobione' THEN now() END WHERE feedback_id = %s""",
                           (status, status, feedback_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "nie ma takiego zgłoszenia")
    return {"ok": True}


# --- zespół: ulubione i komentarze ---------------------------------------------------------------

def _listing_key(key: str) -> tuple[str, str]:
    source, _, listing = (key or "").partition(":")
    if not source or not listing or len(key) > 200:
        raise HTTPException(400, "klucz ogłoszenia: źródło:numer")
    return source, listing


def _keys(keys: str | list[str]) -> list[str]:
    items = keys.split(",") if isinstance(keys, str) else keys
    items = [k for k in (i.strip() for i in items) if k][:20]
    for k in items:
        _listing_key(k)
    if not items:
        raise HTTPException(400, "brak kluczy ogłoszeń")
    return items


@app.post("/api/favorites")
def favorite_add(request: Request, key: str = Body(..., embed=True)):
    source, listing = _listing_key(key)
    with _conn() as conn:
        conn.execute("""INSERT INTO app.favorites (user_email, source_id, source_listing_id) VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING""", (_user(request), source, listing))
    return {"ok": True}


@app.post("/api/favorites/remove")
def favorite_remove(request: Request, keys: list[str] = Body(..., embed=True)):
    """Zdejmuje gwiazdkę z całej działki (wszystkie jej ogłoszenia)."""
    with _conn() as conn:
        conn.execute("""DELETE FROM app.favorites WHERE user_email = %s
                        AND source_id || ':' || source_listing_id = ANY(%s)""", (_user(request), _keys(keys)))
    return {"ok": True}


@app.get("/api/favorites")
def favorites(request: Request, sort: str = "newest"):
    """Moje ulubione działki ze wszystkich gmin, także te, które już zniknęły z portali."""
    if sort not in SORTS:
        raise HTTPException(400, f"sort: jedno z {', '.join(SORTS)}")
    scope = """l.property_key IN (SELECT l2.property_key FROM links l2 JOIN app.favorites fv
                 USING (source_id, source_listing_id) WHERE fv.user_email = %(me)s)"""
    return _offers(scope, ["true"], {"me": _user(request), "limit": 1000}, sort)


@app.get("/api/comments")
def comments(request: Request, keys: str):
    rows = _rows("""SELECT comment_id AS id, user_email AS author, body, created_at,
                           user_email = %(me)s AS mine
                    FROM app.comments WHERE deleted_at IS NULL
                      AND source_id || ':' || source_listing_id = ANY(%(k)s)
                    ORDER BY created_at""", {"k": _keys(keys), "me": _user(request)})
    return rows


@app.post("/api/comments")
def comment_add(request: Request, key: str = Body(...), body: str = Body(...)):
    source, listing = _listing_key(key)
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise HTTPException(400, "komentarz: od 1 do 2000 znaków")
    with _conn() as conn:
        row = conn.execute("""INSERT INTO app.comments (source_id, source_listing_id, user_email, body)
                              VALUES (%s, %s, %s, %s) RETURNING comment_id AS id""",
                           (source, listing, _user(request), body)).fetchone()
    return row


@app.delete("/api/comments/{comment_id}")
def comment_delete(request: Request, comment_id: int):
    """Usunąć można tylko własny komentarz (zostaje w bazie z datą usunięcia)."""
    with _conn() as conn:
        cur = conn.execute("""UPDATE app.comments SET deleted_at = now()
                              WHERE comment_id = %s AND user_email = %s AND deleted_at IS NULL""",
                           (comment_id, _user(request)))
    if cur.rowcount == 0:
        raise HTTPException(404, "nie ma takiego komentarza albo nie jest Twój")
    return {"ok": True}

def _check_teryt(teryt: str) -> None:
    if not (teryt.isdigit() and len(teryt) == 7):
        raise HTTPException(400, "TERYT gminy to 7 cyfr")


def serve() -> None:  # pragma: no cover - punkt wejścia kontenera
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":  # pragma: no cover
    serve()

