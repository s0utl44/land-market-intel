"""Strona Radar Działek: API na danych z bazy + statyczny frontend (web_static/).

Uruchomienie: uvicorn lmi.web:app --host 0.0.0.0 --port 8080
Dostęp chroni Traefik (hasło na wejściu), aplikacja sama nie ma logowania.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

from .db import DEFAULT_DSN
from .metrics import MIN_SUPPLY_FOR_RANK

STATIC = Path(__file__).parent / "web_static"

app = FastAPI(title="Radar Działek", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


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


@app.get("/api/me")
def me(request: Request):
    """Kto jest zalogowany. Nagłówek ustawia Traefik z odpowiedzi oauth2-proxy (logowanie Google);
    przy bramce z hasłem go nie ma."""
    email = request.headers.get("x-auth-request-email") or request.headers.get("x-auth-request-user")
    return {"email": email, "logout_url": "/oauth2/sign_out?rd=%2F" if email else None}


@app.get("/api/overview")
def overview():
    run = _rows("""SELECT finished_at, status, rows_written, message FROM scrape.runs
                   WHERE status IN ('ok', 'warning') ORDER BY run_id DESC LIMIT 1""")
    attempt = _rows("""SELECT started_at, finished_at, status, message FROM scrape.runs
                       ORDER BY run_id DESC LIMIT 1""")
    weekly = _rows("""
        SELECT count(DISTINCT week_start) AS weeks,
               max(week_start) AS last_week
        FROM mart.weekly_region_metrics""")[0]
    latest = _rows("""
        SELECT coalesce(sum(active_supply), 0) AS active_offers,
               coalesce(sum(new_listings), 0)  AS new_this_week,
               count(*) FILTER (WHERE active_supply > 0) AS municipalities
        FROM mart.weekly_region_metrics
        WHERE week_start = (SELECT max(week_start) FROM mart.weekly_region_metrics)""")[0]
    last_day = _rows("SELECT max(observed_at) AS d FROM core.listing_observations")[0]["d"]
    return {
        "last_run": run[0] if run else None,          # ostatni udany przebieg
        "latest_attempt": attempt[0] if attempt else None,  # ostatnia próba, także nieudana
        "last_observed": last_day,
        "weeks_of_data": weekly["weeks"],
        "last_week": weekly["last_week"],
        "min_supply_for_rank": MIN_SUPPLY_FOR_RANK,
        **latest,
    }


@app.get("/api/ranking")
def ranking():
    return _rows("""
        SELECT municipality_teryt AS teryt, municipality_name AS name, rank, opportunity_score AS score,
               avg_absorption_rate AS absorption, price_trend_pct AS price_trend,
               avg_discounted_share AS discounted, median_days_to_disappear AS days,
               latest_active_supply AS supply, latest_median_price_per_m2 AS ppm2, weeks_observed AS weeks,
               latest_median_listing_age_days AS age
        FROM mart.region_scores
        ORDER BY rank NULLS LAST, latest_active_supply DESC NULLS LAST, municipality_name""")


@app.get("/api/municipality/{teryt}/weekly")
def municipality_weekly(teryt: str):
    _check_teryt(teryt)
    rows = _rows("""
        SELECT week_start, active_supply AS supply, new_listings AS new, disappeared_listings AS gone,
               median_price_per_m2 AS ppm2, absorption_rate AS absorption,
               discounted_share AS discounted, median_days_to_disappear AS days
        FROM mart.weekly_region_metrics WHERE municipality_teryt = %(t)s ORDER BY week_start""", {"t": teryt})
    if not rows:
        raise HTTPException(404, "Brak danych dla tej gminy")
    # punkt odniesienia: mediana z gmin z wystarczającą liczbą ofert, tydzień po tygodniu
    benchmark = _rows("""
        SELECT week_start,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY median_price_per_m2) AS ppm2,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY absorption_rate) AS absorption,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY discounted_share) AS discounted,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY active_supply) AS supply
        FROM mart.weekly_region_metrics WHERE active_supply >= %(m)s
        GROUP BY week_start ORDER BY week_start""", {"m": MIN_SUPPLY_FOR_RANK})
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
}


@app.get("/api/municipality/{teryt}/offers")
def municipality_offers(
    teryt: str,
    land_use: str | None = None,
    min_area: float | None = Query(None, ge=0),
    max_area: float | None = Query(None, ge=0),
    max_ppm2: float | None = Query(None, ge=0),
    min_age_days: int | None = Query(None, ge=0),
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
            WHERE o.municipality_teryt = %(t)s
        ),
        p AS (
            SELECT property_key,
                   min(observed_at) AS first_seen, max(observed_at) AS last_seen,
                   count(DISTINCT source_id) AS portals,
                   (array_agg(price_pln ORDER BY observed_at))[1]       AS first_price,
                   (array_agg(price_pln ORDER BY observed_at DESC))[1]  AS price,
                   (array_agg(area_m2 ORDER BY observed_at DESC))[1]    AS area,
                   (array_agg(land_use ORDER BY observed_at DESC))[1]   AS land_use,
                   (array_agg(url ORDER BY observed_at DESC))[1]        AS url,
                   bool_or(lat IS NOT NULL)                             AS precise,
                   bool_or(in_latest)                                   AS active,
                   min(listed_at)                                       AS listed_at,
                   max(pushed_up_at)                                    AS pushed_up_at,
                   (array_agg(source_listing_id ORDER BY observed_at DESC)
                        FILTER (WHERE source_id = 'otodom'))[1]          AS otodom_id
            FROM o GROUP BY property_key
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
                   (SELECT (e->>'price')::numeric FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->>'price' IS NOT NULL ORDER BY e->>'date' LIMIT 1) AS hist_first_price,
                   (SELECT (e->>'date')::date FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->'changes' ? 'FIRST_PUBLISHED' ORDER BY e->>'date' LIMIT 1) AS hist_published,
                   (SELECT count(*) FROM jsonb_array_elements(d.detail->'history') e
                     WHERE e->'changes' ? 'ACTIVATED')::int AS relists
            FROM p JOIN scrape.otodom_details d ON d.ad_id = p.otodom_id
        ),
        f AS (
            SELECT p.*, c.history, oh.otodom_history, oh.views, oh.saved, coalesce(oh.relists, 0) AS relists,
                   oh.land_use_source,
                   round(price / area, 1) AS ppm2,
                   -- zmiana ceny od pierwszej znanej: z historii Otodom, a bez niej od pierwszej obserwacji
                   round((price / coalesce(oh.hist_first_price, first_price) - 1) * 100, 1) AS price_change,
                   least(first_seen, coalesce(listed_at, oh.hist_published, first_seen)) AS start_date,
                   last_seen - least(first_seen, coalesce(listed_at, oh.hist_published, first_seen)) AS age_days
            FROM p LEFT JOIN changes c USING (property_key) LEFT JOIN oh USING (property_key)
        )
        SELECT property_key AS id, price, area, ppm2, land_use, url, portals, precise,
               first_seen, listed_at, pushed_up_at, start_date, age_days, price_change, history,
               otodom_history, views, saved, relists, land_use_source
        FROM f WHERE {' AND '.join(where)}
        ORDER BY {SORTS[sort]}, property_key
        LIMIT %(limit)s""", params)
    return rows


def _check_teryt(teryt: str) -> None:
    if not (teryt.isdigit() and len(teryt) == 7):
        raise HTTPException(400, "TERYT gminy to 7 cyfr")


def serve() -> None:  # pragma: no cover - punkt wejścia kontenera
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":  # pragma: no cover
    serve()

