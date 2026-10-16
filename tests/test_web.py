"""Strona: API na prawdziwym PostgreSQL z danymi syntetycznymi."""
import pytest

from lmi import db, synthetic

pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_conn, synthetic_data, monkeypatch):
    from fastapi.testclient import TestClient

    from lmi import web

    for src in synthetic.SOURCES:
        db.add_source(pg_conn, src, src)
        db.approve_source(pg_conn, src, "syntetyczne", "pytest")
        db.import_csv(pg_conn, src, synthetic_data["paths"][src])
    run_id, _ = db.run_dedup(pg_conn)
    db.run_metrics(pg_conn, run_id)
    monkeypatch.setenv("LMI_DATABASE_URL", pg_conn.test_url)
    return TestClient(web.app)


def test_index_and_logo(client):
    r = client.get("/")
    assert r.status_code == 200 and "Radar" in r.text and "currentColor" in r.text
    assert client.get("/static/logo-wre.svg").status_code == 200


def test_overview(client):
    d = client.get("/api/overview").json()
    assert d["weeks_of_data"] == 26 and d["municipalities"] == 3 and d["active_offers"] > 100
    assert d["last_run"] is None  # brak przebiegów scrapera w danych syntetycznych


def test_ranking(client):
    rows = client.get("/api/ranking").json()
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert rows[0]["name"] == "Syntetyczna Rozwojowa" and rows[0]["supply"] > 0


def test_weekly_with_benchmark(client):
    d = client.get("/api/municipality/9900011/weekly").json()
    assert len(d["weeks"]) == 26 and len(d["benchmark"]) == 26
    assert client.get("/api/municipality/9999999/weekly").status_code == 404


def test_offers_are_active_and_filtered(client):
    rows = client.get("/api/municipality/9900011/offers").json()
    assert rows and all(r["ppm2"] is not None for r in rows)
    assert [r["ppm2"] for r in rows] == sorted(r["ppm2"] for r in rows)
    # tylko oferty widziane w ostatnim pobraniu
    active = client.get("/api/overview").json()
    assert len(rows) <= active["active_offers"]
    big = client.get("/api/municipality/9900011/offers", params={"min_area": 1500, "land_use": "budowlana"}).json()
    assert all(r["area"] >= 1500 and r["land_use"] == "budowlana" for r in big)
    assert len(big) < len(rows)


def test_offers_rejects_bad_input(client):
    assert client.get("/api/municipality/abc/offers").status_code == 400
    assert client.get("/api/municipality/9900011/offers", params={"sort": "price; DROP TABLE x"}).status_code == 400
    assert client.get("/api/municipality/9900011/offers", params={"limit": 5000}).status_code == 422


def test_me_reads_identity_from_proxy_header(client):
    assert client.get("/api/me").json() == {"email": None, "logout_url": None}
    d = client.get("/api/me", headers={"X-Auth-Request-Email": "jan@wrenieruchomosci.pl"}).json()
    assert d["email"] == "jan@wrenieruchomosci.pl" and d["logout_url"].startswith("/oauth2/sign_out")


def test_offers_have_listing_age_and_price_history(client):
    rows = client.get("/api/municipality/9900033/offers", params={"sort": "cut"}).json()
    assert all(r["listed_at"] and r["age_days"] >= 0 for r in rows)
    cut = rows[0]
    assert cut["price_change"] <= -1
    hist = cut["history"]
    assert len(hist) >= 2 and hist[-1]["price"] == cut["price"]
    assert all(a["price"] != b["price"] for a, b in zip(hist, hist[1:]))
    old = client.get("/api/municipality/9900033/offers", params={"min_age_days": 180, "sort": "longest"}).json()
    assert old and all(r["age_days"] >= 180 for r in old)
    assert [r["start_date"] for r in old] == sorted(r["start_date"] for r in old)


def test_ranking_has_listing_age(client):
    rows = client.get("/api/ranking").json()
    assert all(r["age"] is not None for r in rows)


def test_offers_use_otodom_account_history(client, pg_conn, tmp_path):
    import json

    csv = ("source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln,listed_at\n"
           "777,2026-06-29,9900011,Syntetyczna Rozwojowa,1000,500000,2013-05-08\n")
    # ostatni dzień danych syntetycznych to 2026-06-29, więc oferta jest aktywna w źródle "otodom"
    f = tmp_path / "o.csv"
    f.write_text(csv)
    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    db.import_csv(pg_conn, "otodom", f)
    history = [{"date": "2013-05-08", "status": "ACTIVE", "price": None, "changes": ["FIRST_PUBLISHED"]},
               {"date": "2024-01-10", "status": "ACTIVE", "price": 625000.0, "changes": ["PRICE"]},
               {"date": "2025-02-01", "status": "INACTIVE", "price": 625000.0, "changes": ["DEACTIVATED"]},
               {"date": "2025-03-01", "status": "ACTIVE", "price": 625000.0, "changes": ["ACTIVATED"]},
               {"date": "2026-05-01", "status": "ACTIVE", "price": 500000.0, "changes": ["PRICE_DOWN"]}]
    pg_conn.execute("INSERT INTO scrape.otodom_details (ad_id, slug, detail) VALUES ('777', 's', %s)",
                    (json.dumps({"lat": 51.1, "history": history, "stats": {"views": 228, "saved": 3, "at": "2026-06-29"}}),))
    pg_conn.commit()
    run_id, _ = db.run_dedup(pg_conn)
    db.run_metrics(pg_conn, run_id)
    rows = client.get("/api/municipality/9900011/offers", params={"sort": "saved"}).json()
    o = rows[0]
    assert o["saved"] == 3 and o["views"] == 228 and o["relists"] == 1
    assert o["price_change"] == -20.0           # 625 000 -> 500 000 z historii Otodom
    assert o["start_date"] == "2013-05-08" and len(o["otodom_history"]) == 5
