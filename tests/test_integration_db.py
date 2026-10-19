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

    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(make_web())) == 2


def test_daily_pipeline_two_days(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import run_daily
    from lmi.scrapers.http import Blocked
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    web = make_web()
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 16)) == 0
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 0

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

    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=Blocking(), observed_at=date(2026, 10, 18)) == 3
    assert pg_conn.execute("SELECT status FROM scrape.runs ORDER BY run_id DESC LIMIT 1").fetchone()[0] == "blocked"


def test_daily_alerts_on_sudden_drop(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import run_daily
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    web = make_web()
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 16)) == 0
    from fixtures_otodom import search_item, search_page
    web.pages = [search_page([search_item(1)], total_pages=1)]  # nagle tylko 1 z 3
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 5


def test_daily_if_needed_skips_after_success_and_errors_are_logged(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import run_daily
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    day = date.today()
    # ponowna próba po nieudanym ranku: ma się wykonać
    class Broken:
        requests_made = 0

        def get(self, url):
            raise RuntimeError("coś nieprzewidzianego")

    with pytest.raises(RuntimeError):
        run_daily(pg_conn, tmp_path, sources=("otodom",), client=Broken(), observed_at=day)
    status, msg = pg_conn.execute("SELECT status, message FROM scrape.runs ORDER BY run_id DESC LIMIT 1").fetchone()
    assert status == "error" and "nieprzewidzianego" in msg
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(make_web()), observed_at=day, if_needed=True) == 0
    n = pg_conn.execute("SELECT count(*) FROM scrape.runs WHERE status = 'ok'").fetchone()[0]
    assert n == 1
    # po udanym przebiegu kolejna próba "if needed" nic nie robi
    web = make_web()
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=day, if_needed=True) == 0
    assert pg_conn.execute("SELECT count(*) FROM scrape.runs").fetchone()[0] == 2


def test_blocked_source_does_not_stop_others(pg_conn, tmp_path):
    from datetime import date

    from fixtures_gratka import detail_page as g_detail, node, search_page as g_search
    from lmi.daily import run_daily
    from lmi.scrapers.http import Blocked
    from test_gratka import Web as GratkaWeb

    for src, name in (("otodom", "Otodom"), ("gratka", "Gratka")):
        db.add_source(pg_conn, src, name)
        db.approve_source(pg_conn, src, "test", "pytest")
    gweb = GratkaWeb(pages=[g_search([node(1), node(2, area="900")], total=2)],
                     details={"1": g_detail(), "2": g_detail(title="Działka rolna")},
                     communes={"16.155000,51.285100": "0\n020905_2|Miłkowice"})

    class Client:
        requests_made = 0

        def get(self, url):
            if "otodom.pl" in url:
                raise Blocked("403")
            return gweb.get(url)

    code = run_daily(pg_conn, tmp_path, sources=("otodom", "gratka"), client=Client(), observed_at=date(2026, 10, 17))
    assert code == 3
    runs = dict(pg_conn.execute("SELECT source_id, status FROM scrape.runs").fetchall())
    assert runs == {"otodom": "blocked", "gratka": "ok"}
    assert pg_conn.execute("SELECT count(*) FROM core.listing_observations WHERE source_id='gratka'").fetchone()[0] == 2
    assert pg_conn.execute("SELECT count(*) FROM core.dedup_runs").fetchone()[0] == 1
    assert pg_conn.execute("SELECT count(*) FROM scrape.portal_details WHERE source_id='gratka'").fetchone()[0] == 2


def test_source_already_running_is_skipped(pg_conn, tmp_path):
    from datetime import date

    from lmi.daily import _SourceLock, run_daily
    from test_otodom import make_web

    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    held = _SourceLock(tmp_path, "otodom")
    assert held.acquire()
    web = make_web()
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 0
    assert web.calls == []  # nic nie pobrano
    held.release()
    assert run_daily(pg_conn, tmp_path, sources=("otodom",), client=_FakeClient(web), observed_at=date(2026, 10, 17)) == 0
    assert web.calls


def test_unapproved_default_source_is_skipped(pg_conn, tmp_path, monkeypatch):
    from lmi.daily import run_daily
    from test_otodom import make_web

    # nowy portal na domyślnej liście, jeszcze niezatwierdzony: codzienny przebieg go pomija bez błędu
    monkeypatch.setenv("LMI_SOURCES", "nieruchomosci-online")
    assert run_daily(pg_conn, tmp_path, client=_FakeClient(make_web())) == 0
    # wywołany wprost nadal zgłasza brak zatwierdzenia
    assert run_daily(pg_conn, tmp_path, sources=("nieruchomosci-online",), client=_FakeClient(make_web())) == 2


@pytest.mark.integration
def test_excluded_listings_are_left_out_of_dedup(pg_conn, synthetic_data):
    from lmi import db as _db

    for src in ("portal_a",):
        _db.add_source(pg_conn, src, src)
        _db.approve_source(pg_conn, src, "test", "pytest")
        _db.import_csv(pg_conn, src, synthetic_data["paths"][src])
    before = {l.source_listing_id for l in _db.run_dedup(pg_conn)[1]}
    victim = sorted(before)[0]
    assert _db.exclude_listings(pg_conn, "portal_a", [victim, victim], "archiwalne") == 1
    after = {l.source_listing_id for l in _db.run_dedup(pg_conn)[1]}
    assert victim not in after and len(after) == len(before) - 1


@pytest.mark.integration
def test_backfill_features_updates_active_offers(pg_conn, tmp_path):
    import json

    from lmi import backfill, db as _db

    _db.add_source(pg_conn, "adresowo", "Adresowo")
    _db.approve_source(pg_conn, "adresowo", "test", "pytest")
    f = tmp_path / "a.csv"
    f.write_text("source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln,url\n"
                 "1,2026-10-18,0223043,Kąty,1000,200000,https://adresowo.example/o/1\n")
    _db.import_csv(pg_conn, "adresowo", f)
    pg_conn.execute("INSERT INTO scrape.portal_details (source_id, ad_id, url, detail) VALUES ('adresowo', '1', 'u', %s)",
                    (json.dumps({"lat": 51.0, "lon": 17.0, "features": {"seller": None, "v": 1}}),))
    pg_conn.commit()
    page = ('<script type="application/ld+json">{"@graph": [{"@type": "Offer", "price": "200000"},'
            '{"@type": "Place", "geo": {"latitude": "51.0", "longitude": "17.0"}}]}</script>'
            '<div class="min-w-0"> Oferta bezpośrednio od właściciela <span>x</span></div>')
    st = backfill.run(pg_conn, "adresowo", lambda url: page)
    assert st["done"] == 1 and st["private"] == 1
    d = pg_conn.execute("SELECT detail FROM scrape.portal_details WHERE ad_id = '1'").fetchone()[0]
    assert d["features"]["seller"] == "prywatny" and d["features"]["v"] == backfill.FEATURES_V
    assert backfill.pending(pg_conn, "adresowo") == []
