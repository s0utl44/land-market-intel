"""Strona Radar Działek: API na danych z bazy + statyczny frontend (web_static/).

Uruchomienie: uvicorn lmi.web:app --host 0.0.0.0 --port 8080
Dostęp chroni Traefik (hasło na wejściu), aplikacja sama nie ma logowania.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
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


TEAM_USER = "zespół"  # przy wspólnym haśle (bez logowania Google) wszyscy są jednym użytkownikiem


def _user(request: Request) -> str:
    """Kto korzysta ze strony. Nagłówki ustawia Traefik: X-Auth-Request-Email z logowania Google
    (oauth2-proxy), X-Auth-Request-User z bramki z hasłem (login osoby). Bez nich: wspólny „zespół”."""
    who = request.headers.get("x-auth-request-email") or request.headers.get("x-auth-request-user")
    return (who or TEAM_USER).strip().lower()


def _admins() -> set[str]:
    """Kto widzi zgłoszenia: LMI_ADMINS w .env (loginy z bramki albo e-maile Google, po przecinku)."""
    return {a.strip().lower() for a in os.environ.get("LMI_ADMINS", "").split(",") if a.strip()}


def _require_admin(request: Request) -> None:
    if _user(request) not in _admins():
        raise HTTPException(403, "tylko dla administratora (LMI_ADMINS)")


@app.get("/api/me")
def me(request: Request):
    email = request.headers.get("x-auth-request-email")
    return {"email": email, "user": _user(request), "is_admin": _user(request) in _admins(),
            "logout_url": "/oauth2/sign_out?rd=%2F" if email else None}


@app.get("/api/overview")
def overview():
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
        "sources": per_source,
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
               latest_median_listing_age_days AS age, t.tx_12m, t.tx_ppm2
        FROM mart.region_scores
        LEFT JOIN (
            -- transakcje samym gruntem pod zabudowę z ostatnich 12 miesięcy danych RCN
            SELECT gmina_teryt, count(*) AS tx_12m,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY ppm2) AS tx_ppm2
            FROM mart.rcn_land_transactions
            WHERE buildable AND ppm2 BETWEEN %(lo)s AND %(hi)s
              AND doc_date > (SELECT max(doc_date) FROM scrape.rcn_parcels) - 365
            GROUP BY gmina_teryt
        ) t ON t.gmina_teryt = municipality_teryt
        ORDER BY rank NULLS LAST, latest_active_supply DESC NULLS LAST, municipality_name""", PPM2_RANGE)


# zł/m² poza tym zakresem to zwykle drogi, udziały albo błędy w rejestrze
PPM2_RANGE = {"lo": 5, "hi": 5000}


@app.get("/api/municipality/{teryt}/transactions")
def municipality_transactions(teryt: str, limit: int = Query(50, ge=1, le=500)):
    """Ceny transakcyjne gruntów z RCN: podsumowanie 12 miesięcy, kwartały i ostatnie akty."""
    _check_teryt(teryt)
    p = {"t": teryt, "limit": limit, **PPM2_RANGE}
    summary = _rows("""
        WITH last AS (SELECT max(doc_date) AS d FROM scrape.rcn_parcels)
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
                   (array_agg(price_pln ORDER BY observed_at DESC))[1]  AS price,
                   (array_agg(area_m2 ORDER BY observed_at DESC))[1]    AS area,
                   (array_agg(land_use ORDER BY observed_at DESC))[1]   AS land_use,
                   (array_agg(url ORDER BY observed_at DESC))[1]        AS url,
                   bool_or(lat IS NOT NULL)                             AS precise,
                   bool_or(in_latest)                                   AS active,
                   min(listed_at)                                       AS listed_at,
                   max(pushed_up_at)                                    AS pushed_up_at,
                   (array_agg(source_listing_id ORDER BY observed_at DESC)
                        FILTER (WHERE source_id = 'otodom'))[1]          AS otodom_id,
                   (array_agg(source_listing_id ORDER BY observed_at DESC)
                        FILTER (WHERE source_id = 'gratka'))[1]          AS gratka_id,
                   (array_agg(source_id ORDER BY observed_at DESC, source_id))[1]          AS source,
                   (array_agg(source_listing_id ORDER BY observed_at DESC, source_id))[1]  AS source_listing_id,
                   array_agg(DISTINCT source_id)                         AS sources,
                   array_agg(DISTINCT source_id || ':' || source_listing_id) AS listing_keys,
                   (array_agg(municipality_name ORDER BY observed_at DESC))[1] AS municipality,
                   (array_agg(municipality_teryt ORDER BY observed_at DESC))[1] AS teryt
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
            FROM p LEFT JOIN changes c USING (property_key) LEFT JOIN oh USING (property_key)
                   LEFT JOIN gv USING (property_key)
                   LEFT JOIN scrape.portal_details pd
                          ON pd.source_id = p.source AND pd.ad_id = p.source_listing_id
        )
        SELECT property_key AS id, price, area, ppm2, land_use, url, portals, precise, source, sources,
               first_seen, listed_at, pushed_up_at, start_date, age_days, price_change, history,
               otodom_history, views, views_source, views_per_day, saved, relists, land_use_source,
               active, municipality, teryt, listing_keys,
               -- zespół: ulubione (moje / ile osób, kto) i liczba komentarzy do tej działki
               EXISTS (SELECT 1 FROM app.favorites fv WHERE fv.user_email = %(me)s
                         AND fv.source_id || ':' || fv.source_listing_id = ANY(listing_keys)) AS fav,
               (SELECT array_agg(DISTINCT fv.user_email ORDER BY fv.user_email) FROM app.favorites fv
                 WHERE fv.source_id || ':' || fv.source_listing_id = ANY(listing_keys)) AS fav_users,
               (SELECT count(*) FROM app.comments c WHERE c.deleted_at IS NULL
                 AND c.source_id || ':' || c.source_listing_id = ANY(listing_keys))::int AS comments
        FROM (SELECT *, scrape.views_per_day(views_log, start_date) AS views_per_day FROM f) f WHERE {' AND '.join(where)}
        ORDER BY {SORTS[sort]}, property_key
        LIMIT %(limit)s""", params)
    return rows


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
    ctx = {k: str(v)[:300] for k, v in (context or {}).items()
           if k in ("gmina", "teryt", "widok", "adres", "przegladarka", "ekran", "oferta") and v not in (None, "")}
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
        ctx = ", ".join(f"{k}: {v}" for k, v in (r["context"] or {}).items())
        when = r["created_at"].strftime("%Y-%m-%d %H:%M") if hasattr(r["created_at"], "strftime") else r["created_at"]
        out.append(f"#{r['id']} [{r['kind']}] {when} · {r['author']}" + (f" · {r['status']}" if r["status"] != "nowe" else ""))
        out.append(r["body"])
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

