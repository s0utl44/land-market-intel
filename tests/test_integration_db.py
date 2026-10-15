"""Testy na prawdziwym PostgreSQL+PostGIS. Uruchom: LMI_TEST_DATABASE_URL=postgresql://... pytest"""
import psycopg
import pytest

from lmi import db

pytestmark = pytest.mark.integration

CSV = (
    "source_listing_id,observed_at,municipality_teryt,municipality_name,parcel_id,lat,lon,area_m2,price_pln\n"
    "A1,2026-03-02,1465011,Testowa,,52.2,21.0,1000,100000\n"
    "A1,2026-03-09,1465011,Testowa,,52.2,21.0,1000,95000\n"
    "A2,2026-03-02,1465011,Testowa,,52.3,21.1,800,90000\n"
)


@pytest.fixture
def approved(pg_conn):
    db.add_source(pg_conn, "src", "Źródło testowe")
    db.approve_source(pg_conn, "src", "test", "pytest")
    return pg_conn


def test_unapproved_source_is_rejected(pg_conn, tmp_path):
    db.add_source(pg_conn, "src", "Źródło testowe")
    f = tmp_path / "x.csv"
    f.write_text(CSV)
    with pytest.raises(db.ImportRejected, match="nie jest zatwierdzone"):
        db.import_csv(pg_conn, "src", f)


def test_unknown_source_is_rejected(pg_conn, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text(CSV)
    with pytest.raises(db.ImportRejected, match="nie jest zarejestrowane"):
        db.import_csv(pg_conn, "nope", f)


def test_approval_requires_legal_basis(pg_conn):
    db.add_source(pg_conn, "src", "x")
    with pytest.raises(psycopg.errors.CheckViolation):
        pg_conn.execute("UPDATE core.sources SET approved = true WHERE source_id = 'src'")
    pg_conn.rollback()


def test_import_and_geometry(approved, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text(CSV)
    r = db.import_csv(approved, "src", f)
    assert (r.rows_in_file, r.rows_inserted, r.rows_duplicate) == (3, 3, 0)
    dist = approved.execute(
        """SELECT ST_Distance(a.geom, b.geom) FROM core.listing_observations a, core.listing_observations b
           WHERE a.source_listing_id = 'A1' AND b.source_listing_id = 'A2' LIMIT 1"""
    ).fetchone()[0]
    assert 10_000 < dist < 16_000  # ~13.5 km


def test_same_file_twice_is_rejected(approved, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text(CSV)
    db.import_csv(approved, "src", f)
    with pytest.raises(db.ImportRejected, match="już zaimportowany"):
        db.import_csv(approved, "src", f)


def test_overlapping_file_counts_duplicates(approved, tmp_path):
    f1, f2 = tmp_path / "1.csv", tmp_path / "2.csv"
    f1.write_text(CSV)
    f2.write_text(CSV + "A3,2026-03-09,1465011,Testowa,,,,500,40000\n")
    db.import_csv(approved, "src", f1)
    r = db.import_csv(approved, "src", f2)
    assert (r.rows_inserted, r.rows_duplicate) == (1, 3)
    assert approved.execute("SELECT count(*) FROM core.listing_observations").fetchone()[0] == 4


def test_invalid_file_is_rejected_atomically(approved, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text(CSV + "A9,zła-data,1465011,Testowa,,,,500,40000\n")
    with pytest.raises(db.ImportRejected, match="1 błędnych"):
        db.import_csv(approved, "src", f)
    assert approved.execute("SELECT count(*) FROM core.listing_observations").fetchone()[0] == 0
    r = db.import_csv(approved, "src", f, allow_partial=True)
    assert r.rows_inserted == 3


@pytest.mark.parametrize("sql", [
    "UPDATE core.listing_observations SET price_pln = 1",
    "DELETE FROM core.listing_observations",
    "TRUNCATE core.listing_observations CASCADE",
    "DELETE FROM core.import_batches",
])
def test_core_is_append_only(approved, tmp_path, sql):
    f = tmp_path / "x.csv"
    f.write_text(CSV)
    db.import_csv(approved, "src", f)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        approved.execute(sql)
    approved.rollback()


def test_full_pipeline_writes_marts(approved, synthetic_data):
    from lmi import synthetic

    for src in synthetic.SOURCES:
        if src != "src":
            db.add_source(approved, src, src)
            db.approve_source(approved, src, "syntetyczne", "pytest")
        db.import_csv(approved, src, synthetic_data["paths"][src])
    run_id, _ = db.run_dedup(approved)
    run2, _ = db.run_dedup(approved)
    assert run2 == run_id + 1  # kolejne uruchomienia nie nadpisują poprzednich
    weekly, scores = db.run_metrics(approved)
    n_weekly = approved.execute("SELECT count(*) FROM mart.weekly_region_metrics").fetchone()[0]
    assert n_weekly == len(weekly) == 3 * 26
    top = approved.execute("SELECT municipality_name, dedup_run_id FROM mart.region_scores WHERE rank = 1").fetchone()
    assert top == ("Syntetyczna Rozwojowa", run2)
    db.run_metrics(approved)  # przeliczenie jest idempotentne
    assert approved.execute("SELECT count(*) FROM mart.weekly_region_metrics").fetchone()[0] == n_weekly


class _FakeClient:
    def __init__(self, web):
        self.web, self.requests_made = web, 0

    def get(self, url):
        self.requests_made += 1
        return self.web.get(url)


def test_daily_requires_approved_source(pg_conn, tmp_path):
    from lmi.daily import run_daily
    from test_otodom import make_web

    assert run_daily(pg_conn, tmp_path, client=_FakeClient(make_web())) == 2


def test_daily_pipeline_two_days(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import run_daily
    from lmi.scrapers.http import Blocked
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    web = make_web()
    assert run_daily(pg_conn, tmp_path, client=_FakeClient(web), observed_at=date(2026, 10, 16)) == 0
    assert run_daily(pg_conn, tmp_path, client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 0

    n_obs = pg_conn.execute("SELECT count(*) FROM core.listing_observations WHERE source_id='otodom'").fetchone()[0]
    assert n_obs == 6  # 3 ogłoszenia x 2 dni
    assert pg_conn.execute("SELECT count(*) FROM scrape.otodom_details").fetchone()[0] == 4
    assert pg_conn.execute("SELECT count(*) FROM mart.weekly_region_metrics").fetchone()[0] > 0
    statuses = [r[0] for r in pg_conn.execute("SELECT status FROM scrape.runs ORDER BY run_id")]
    assert statuses == ["ok", "ok"]

    # blokada: przebieg kończy się kodem 3 i wpisem w dzienniku, bez importu
    class Blocking:
        requests_made = 0

        def get(self, url):
            raise Blocked("403")

    assert run_daily(pg_conn, tmp_path, client=Blocking(), observed_at=date(2026, 10, 18)) == 3
    assert pg_conn.execute("SELECT status FROM scrape.runs ORDER BY run_id DESC LIMIT 1").fetchone()[0] == "blocked"


def test_daily_alerts_on_sudden_drop(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import run_daily
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    web = make_web()
    assert run_daily(pg_conn, tmp_path, client=_FakeClient(web), observed_at=date(2026, 10, 16)) == 0
    from fixtures_otodom import search_item, search_page
    web.pages = [search_page([search_item(1)], total_pages=1)]  # nagle tylko 1 z 3
    assert run_daily(pg_conn, tmp_path, client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 5
