"""Konfiguruje świeży Metabase: konto admina, połączenie z bazą lmi i dashboard z 8 wykresami.

Użycie (po `docker compose up -d`):
    MB_ADMIN_EMAIL=ty@example.com MB_ADMIN_PASSWORD='...' python metabase/setup_dashboard.py

Testowane z Metabase v0.50.x. Skrypt jest idempotentny tylko w zakresie konfiguracji
konta: przy ponownym uruchomieniu loguje się i tworzy NOWY dashboard.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

MB_URL = os.environ.get("MB_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.environ.get("MB_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("MB_ADMIN_PASSWORD")

# Metabase łączy się z bazą z wnętrza sieci docker compose, stąd host "db".
DB_DETAILS = {
    "host": os.environ.get("LMI_DB_HOST", "db"),
    "port": int(os.environ.get("LMI_DB_PORT", "5432")),
    "dbname": "lmi",
    "user": "lmi",
    "password": os.environ.get("LMI_DB_PASSWORD", "lmi"),
    "ssl": False,
}

REGION_FILTER = "[[AND municipality_name = {{region}}]]"


def weekly_query(column: str) -> str:
    return (
        f"SELECT week_start, municipality_name, {column}\n"
        f"FROM mart.weekly_region_metrics\nWHERE 1 = 1 {REGION_FILTER}\n"
        f"ORDER BY week_start"
    )


# (nazwa, SQL, typ wykresu, kolumna wartości lub None dla tabeli, szerokość, wysokość)
CARDS = [
    ("Ranking gmin (opportunity score)",
     "SELECT rank AS \"#\", municipality_name AS gmina, opportunity_score AS score,\n"
     "       avg_absorption_rate AS absorpcja, price_trend_pct AS trend_cen,\n"
     "       avg_discounted_share AS przecenione, median_days_to_disappear AS dni_do_znikniecia\n"
     f"FROM mart.region_scores WHERE 1 = 1 {REGION_FILTER}\nORDER BY rank",
     "table", None, 24, 5),
    ("Aktywna podaż (liczba działek)", weekly_query("active_supply"), "line", "active_supply", 12, 6),
    ("Mediana ceny [zł/m²]", weekly_query("median_price_per_m2"), "line", "median_price_per_m2", 12, 6),
    ("Nowe ogłoszenia / tydzień", weekly_query("new_listings"), "bar", "new_listings", 12, 6),
    ("Zniknięte ogłoszenia / tydzień", weekly_query("disappeared_listings"), "bar", "disappeared_listings", 12, 6),
    ("Wskaźnik absorpcji", weekly_query("absorption_rate"), "line", "absorption_rate", 12, 6),
    ("Odsetek przecenionych ofert", weekly_query("discounted_share"), "line", "discounted_share", 12, 6),
    ("Mediana dni do zniknięcia", weekly_query("median_days_to_disappear"), "line", "median_days_to_disappear", 24, 6),
]


def api(method: str, path: str, body: dict | None = None, session: str | None = None):
    req = urllib.request.Request(
        MB_URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"X-Metabase-Session": session} if session else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {exc.read().decode()[:500]}")
    return json.loads(raw) if raw else None


def wait_for_metabase(timeout_s: int = 300) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(MB_URL + "/api/health", timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return
        except Exception:
            pass
        time.sleep(3)
    raise SystemExit(f"Metabase nie odpowiada pod {MB_URL}")


def login_or_setup() -> str:
    props = api("GET", "/api/session/properties")
    token = props.get("setup-token")
    if token and not props.get("has-user-setup"):
        print("Tworzę konto administratora...")
        res = api("POST", "/api/setup", {
            "token": token,
            "user": {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "first_name": "Admin",
                     "last_name": "LMI", "site_name": "Land Market Intelligence"},
            "prefs": {"site_name": "Land Market Intelligence", "site_locale": "pl", "allow_tracking": False},
        })
        return res["id"]
    return api("POST", "/api/session", {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})["id"]


def ensure_database(session: str) -> int:
    for d in api("GET", "/api/database", session=session)["data"]:
        if d["name"] == "LMI":
            return d["id"]
    print("Dodaję połączenie z bazą LMI...")
    db = api("POST", "/api/database", {"engine": "postgres", "name": "LMI", "details": DB_DETAILS}, session)
    return db["id"]


def create_card(session: str, db_id: int, name: str, sql: str, display: str, value_col: str | None) -> int:
    viz = {}
    if value_col:
        viz = {"graph.dimensions": ["week_start", "municipality_name"], "graph.metrics": [value_col]}
    card = api("POST", "/api/card", {
        "name": name,
        "display": display,
        "visualization_settings": viz,
        "dataset_query": {
            "type": "native",
            "database": db_id,
            "native": {
                "query": sql,
                "template-tags": {
                    "region": {"id": "region", "name": "region", "display-name": "Gmina", "type": "text"},
                },
            },
        },
    }, session)
    return card["id"]


def main() -> int:
    if not ADMIN_PASSWORD:
        print("Ustaw MB_ADMIN_PASSWORD (i najlepiej MB_ADMIN_EMAIL).", file=sys.stderr)
        return 1
    wait_for_metabase()
    session = login_or_setup()
    db_id = ensure_database(session)

    dashboard = api("POST", "/api/dashboard", {
        "name": "Rynki gruntów — porównanie gmin",
        "parameters": [{"id": "region", "name": "Gmina", "slug": "gmina", "type": "string/="}],
    }, session)

    dashcards, row, col = [], 0, 0
    for i, (name, sql, display, value_col, w, h) in enumerate(CARDS):
        card_id = create_card(session, db_id, name, sql, display, value_col)
        if col + w > 24:
            row, col = row + h, 0
        dashcards.append({
            "id": -(i + 1), "card_id": card_id, "row": row, "col": col, "size_x": w, "size_y": h,
            "parameter_mappings": [{"parameter_id": "region", "card_id": card_id,
                                    "target": ["variable", ["template-tag", "region"]]}],
        })
        col += w
        if col >= 24:
            row, col = row + h, 0

    api("PUT", f"/api/dashboard/{dashboard['id']}", {"dashcards": dashcards}, session)
    print(f"Gotowe: {MB_URL}/dashboard/{dashboard['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
