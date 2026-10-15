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
