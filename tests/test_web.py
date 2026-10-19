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
    assert client.get("/static/logo-donehome.svg").status_code == 200


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
    assert client.get("/api/me").json() == {"email": None, "user": "zespół", "is_admin": False, "logout_url": None}
    d = client.get("/api/me", headers={"X-Auth-Request-Email": "jan@donehome.pl"}).json()
    assert d["email"] == "jan@donehome.pl" and d["logout_url"].startswith("/oauth2/sign_out")


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
                    (json.dumps({"lat": 51.1, "history": history, "land_use": "budowlana", "land_use_source": "tytuł",
                                 "stats": {"views": 228, "saved": 3, "at": "2026-06-29"}}),))
    pg_conn.commit()
    run_id, _ = db.run_dedup(pg_conn)
    db.run_metrics(pg_conn, run_id)
    rows = client.get("/api/municipality/9900011/offers", params={"sort": "saved"}).json()
    o = rows[0]
    assert o["saved"] == 3 and o["views"] == 228 and o["relists"] == 1
    assert o["views_source"] == "otodom"
    assert o["price_change"] == -20.0           # 625 000 -> 500 000 z historii Otodom
    assert o["start_date"] == "2013-05-08" and len(o["otodom_history"]) == 5
    assert o["land_use_source"] == "tytuł"
    assert o["source"] == "otodom" and o["sources"] == ["otodom"]

    assert o["features"]["seller"] is None
    pg_conn.execute("""UPDATE scrape.otodom_details SET detail = detail || %s WHERE ad_id = '777'""",
                    (json.dumps({"features": {"seller": "prywatny", "media": ["prąd", "woda"], "access": [],
                                              "params": {"dimensions": "20x50"}}}),))
    pg_conn.commit()
    priv = client.get("/api/municipality/9900011/offers", params={"seller": "prywatny", "media": "prąd+woda"}).json()
    assert [r["id"] for r in priv] == [o["id"]] and priv[0]["features"]["media"] == ["prąd", "woda"]
    assert priv[0]["features"]["params"] == {"otodom": {"dimensions": "20x50"}}
    assert client.get("/api/municipality/9900011/offers", params={"media": "gaz"}).json() == []
    assert client.get("/api/municipality/9900011/offers", params={"seller": "x"}).status_code == 422


def test_overview_reports_failed_attempt(client, pg_conn):
    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    pg_conn.execute("""INSERT INTO scrape.runs (source_id, started_at, status, rows_written)
                       VALUES ('otodom', now() - interval '1 day', 'ok', 4000)""")
    pg_conn.execute("""INSERT INTO scrape.runs (source_id, started_at, status, message)
                       VALUES ('otodom', now(), 'blocked', '403 dla ...')""")
    pg_conn.commit()
    d = client.get("/api/overview").json()
    assert d["last_run"]["status"] == "ok" and d["latest_attempt"]["status"] == "blocked"
    by_src = {x["source"]: x for x in d["sources"]}
    assert by_src["otodom"]["latest"]["status"] == "blocked" and by_src["otodom"]["last_ok"] is not None


def test_gratka_views_and_rate(client, pg_conn, tmp_path):
    import json

    csv = ("source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln,listed_at\n"
           "g1,2026-06-29,9900011,Syntetyczna Rozwojowa,1000,500000,2026-06-19\n"
           "g2,2026-06-29,9900011,Syntetyczna Rozwojowa,1200,400000,2026-06-09\n")
    f = tmp_path / "g.csv"
    f.write_text(csv)
    db.add_source(pg_conn, "gratka", "Gratka")
    db.approve_source(pg_conn, "gratka", "test", "pytest")
    db.import_csv(pg_conn, "gratka", f)
    # g1: dwa pomiary -> przyrost 60 w 3 dni = 20/dzień; g2: jeden pomiar 100 po 20 dniach = 5/dzień
    logs = {"g1": [{"date": "2026-06-26", "views": 40}, {"date": "2026-06-29", "views": 100}],
            "g2": [{"date": "2026-06-29", "views": 100}]}
    for aid, lg in logs.items():
        pg_conn.execute("INSERT INTO scrape.portal_details (source_id, ad_id, url, detail) VALUES ('gratka', %s, 'u', %s)",
                        (aid, json.dumps({"views_log": lg, "stats": {"views": lg[-1]["views"], "at": lg[-1]["date"]}})))
    pg_conn.commit()
    run_id, _ = db.run_dedup(pg_conn)
    db.run_metrics(pg_conn, run_id)
    rows = client.get("/api/municipality/9900011/offers", params={"sort": "views_rate"}).json()
    top = [r for r in rows if r["views_source"] == "gratka"]
    assert [(r["views"], float(r["views_per_day"])) for r in top[:2]] == [(100, 20.0), (100, 5.0)]


def test_team_favorites_and_comments(client):
    kasia = {"x-auth-request-email": "kasia@donehome.pl"}
    piotr = {"x-auth-request-email": "Piotr@donehome.pl"}
    offers = client.get("/api/municipality/9900011/offers", headers=kasia).json()
    o = offers[0]
    assert o["fav"] is False and o["fav_users"] is None and o["comments"] == 0 and o["listing_keys"]
    key = o["listing_keys"][0]
    assert client.post("/api/favorites", json={"key": key}, headers=kasia).status_code == 200
    assert client.post("/api/favorites", json={"key": key}, headers=kasia).status_code == 200  # drugi raz bez błędu
    client.post("/api/favorites", json={"key": o["listing_keys"][-1]}, headers=piotr)
    r = client.post("/api/comments", json={"key": key, "body": "  Właściciel zejdzie do 450 tys.  "}, headers=piotr)
    cid = r.json()["id"]

    mine = {x["id"]: x for x in client.get("/api/municipality/9900011/offers", headers=kasia).json()}[o["id"]]
    assert mine["fav"] is True and mine["comments"] == 1
    assert mine["fav_users"] == ["kasia@donehome.pl", "piotr@donehome.pl"]

    cs = client.get("/api/comments", params={"keys": ",".join(o["listing_keys"])}, headers=kasia).json()
    assert [(c["author"], c["body"], c["mine"]) for c in cs] == [("piotr@donehome.pl",
                                                                  "Właściciel zejdzie do 450 tys.", False)]
    assert client.delete(f"/api/comments/{cid}", headers=kasia).status_code == 404  # nie swój
    assert client.delete(f"/api/comments/{cid}", headers=piotr).status_code == 200

    favs = client.get("/api/favorites", headers=kasia).json()
    assert [f["id"] for f in favs] == [o["id"]] and favs[0]["municipality"] == "Syntetyczna Rozwojowa"
    client.post("/api/favorites/remove", json={"keys": o["listing_keys"]}, headers=kasia)
    assert client.get("/api/favorites", headers=kasia).json() == []
    assert len(client.get("/api/favorites", headers=piotr).json()) == 1


def test_shared_password_is_one_team_user(client):
    assert client.get("/api/me").json()["user"] == "zespół"
    # bramka z hasłem: login osoby z nagłówka Traefika, bez linku wylogowania (to nie Google)
    assert client.get("/api/me", headers={"X-Auth-Request-User": "Kasia"}).json() == \
        {"email": None, "user": "kasia", "is_admin": False, "logout_url": None}
    assert client.post("/api/comments", json={"key": "x", "body": "a"}).status_code == 400
    assert client.post("/api/comments", json={"key": "otodom:1", "body": " "}).status_code == 400


def test_transactions_endpoint_and_ranking(client, pg_conn):
    rows = [("A", "990001_1.1.1", "2025-03-01", 300000, 1000, "budownictwoMieszkanioweJednorodzinne"),
            ("B", "990001_1.1.2", "2025-06-01", 100000, 1000, "terenRolniczy"),
            ("C", "990001_1.1.3", "2025-07-01", 10, 100000, "terenDrogWewnetrznych"),   # 0,0001 zł/m²: odrzucona
            ("D", "990001_1.1.4", "2025-08-01", 500000, 0.1, "budownictwoMieszkanioweJednorodzinne")]  # 0,1 ha
    for tx, parcel, d, price, area, mpzp in rows:
        pg_conn.execute("""INSERT INTO scrape.rcn_parcels (tx_id, parcel_id, gmina_teryt, doc_date, tran_type, tran_price,
                           nier_type, share, mpzp, area_m2, land_use) VALUES (%s, %s, '9900011', %s, 'wolnyRynek', %s,
                           'nieruchomoscGruntowaNiezabudowana', '1/1', %s, %s, 'gruntyRolne')""", (tx, parcel, d, price, mpzp, area))
    pg_conn.commit()
    from lmi import rcn
    rcn.refresh_land(pg_conn)          # strona czyta zmaterializowane transakcje, odświeżane po pobraniu RCN
    d = client.get("/api/municipality/9900011/transactions").json()
    s = d["summary"]
    assert s["tx_12m"] == 3 and s["tx_build_12m"] == 2 and float(s["ppm2_build_12m"]) == 400.0
    assert [r["ppm2"] for r in d["recent"]] == [500, 100, 300] and len(d["quarters"]) == 3
    assert float(d["recent"][0]["area"]) == 1000.0          # powierzchnia w hektarach przeliczona na m²
    rank = {r["teryt"]: r for r in client.get("/api/ranking").json()}
    assert rank["9900011"]["tx_12m"] == 3 and rank["9900011"]["tx_build_12m"] == 2
    assert rank["9900022"]["tx_12m"] is None


def test_feedback_flow(client, monkeypatch):
    monkeypatch.setenv("LMI_ADMINS", "Dlys, szef@donehome.pl")
    kasia = {"X-Auth-Request-User": "kasia"}
    admin = {"X-Auth-Request-User": "dlys"}
    r = client.post("/api/feedback", headers=kasia, json={
        "kind": "błąd", "body": "  Oferta za 450 tys. jest podwójnie  ",
        "context": {"gmina": "Kąty Wrocławskie", "widok": "karta gminy", "haslo": "nie zapisuj",
                    "obszary": "Wykres „Mediana ceny za m²” | Oferta: budowlana, 1050 m²"}})
    fid = r.json()["id"]
    assert client.post("/api/feedback", headers=kasia, json={"kind": "inne", "body": "abc"}).status_code == 400
    assert client.get("/api/feedback", headers=kasia).status_code == 403           # nie admin
    assert client.get("/api/me", headers=admin).json()["is_admin"] is True
    rows = client.get("/api/feedback", headers=admin).json()
    assert [(x["id"], x["author"], x["body"]) for x in rows] == [(fid, "kasia", "Oferta za 450 tys. jest podwójnie")]
    assert "haslo" not in rows[0]["context"] and rows[0]["context"]["gmina"] == "Kąty Wrocławskie"
    txt = client.get("/api/feedback/export", headers=admin).text
    assert f"#{fid} [błąd]" in txt and "gmina: Kąty Wrocławskie" in txt
    assert "  - Wykres „Mediana ceny za m²”\n  - Oferta: budowlana, 1050 m²" in txt
    assert client.post(f"/api/feedback/{fid}/status", headers=admin, json={"status": "zrobione"}).status_code == 200
    assert client.get("/api/feedback", headers=admin).json() == []
    assert len(client.get("/api/feedback", headers=admin, params={"status": "wszystkie"}).json()) == 1


def test_admin_status(client, pg_conn, monkeypatch):
    monkeypatch.setenv("LMI_ADMINS", "x")
    admin = {"X-Auth-Request-User": "x"}
    assert client.get("/api/admin/status").status_code == 403
    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    pg_conn.execute("""INSERT INTO scrape.runs (source_id, started_at, finished_at, status, message)
                       VALUES ('otodom', now(), now(), 'blocked', '403 dla https://www.otodom.pl')""")
    pg_conn.execute("""INSERT INTO scrape.job_status (job, state, started_at, updated_at, message)
                       VALUES ('gratka', 'running', now() - interval '2 hours', now() - interval '1 hour', 'lista, strona 40')""")
    pg_conn.commit()
    d = client.get("/api/admin/status", headers=admin).json()
    titles = [i["title"] for i in d["issues"]]
    assert "Otodom: ostatnie pobieranie nie przeszło" in titles
    assert any("gratka: zadanie nie daje znaku życia" in t for t in titles)
    assert d["problems"] >= 2 and d["jobs"][0]["stale"] is True


def test_job_tracking_writes_progress(pg_conn):
    import logging

    from lmi import jobs

    with jobs.tracked(pg_conn, "rcn", "start") as job:
        logging.getLogger("lmi.rcn").info("rcn: 2020-01: 100 rekordów")
        job.progress("ręczny postęp", force=True)
        job.finish("ok", "zapisano 100 rekordów")
    row = pg_conn.execute("SELECT state, message, finished_at IS NOT NULL FROM scrape.job_status WHERE job = 'rcn'").fetchone()
    assert row == ("ok", "zapisano 100 rekordów", True)
    try:
        with jobs.tracked(pg_conn, "rcn"):
            raise RuntimeError("geoportal padł")
    except RuntimeError:
        pass
    assert pg_conn.execute("SELECT state, message FROM scrape.job_status WHERE job = 'rcn'").fetchone() == \
        ("error", "RuntimeError: geoportal padł")


def test_merge_features_across_portals():
    from lmi.web import merge_features

    f = merge_features([
        {"src": "otodom", "seller": None, "list_seller": "biuro", "media": ["prąd"], "access": ["asfaltowy"],
         "fence": None, "updated_at": "2026-10-01", "params": {"dimensions": "30x50"}},
        {"src": "gratka", "seller": "prywatny", "media": ["woda", "prąd"], "negotiable": True,
         "updated_at": "2026-10-05", "params": {"Media": "prąd, woda"}},
    ])
    assert f["seller"] == "prywatny" and f["media"] == ["prąd", "woda"] and f["negotiable"] is True   # któreś od właściciela
    assert f["updated_at"] == "2026-10-05" and set(f["params"]) == {"otodom", "gratka"}


def test_changes(client):
    d = client.get("/api/changes", params={"days": 7}).json()
    assert d["last_day"] == "2026-06-29" and d["daily"] and d["weekly"]
    day = d["daily"][-1]
    assert day["active"] > 100 and day["new"] >= 0 and day["gone"] >= 0
    assert sum(w["new"] for w in d["weekly"]) > 0 and sum(w["gone"] for w in d["weekly"]) > 0
    assert all(c["change"] < 0 for c in d["cuts"])
    assert all("vs_median" in f for f in d["fresh"]) and isinstance(d["gminy"], list)
    assert client.get("/api/changes", params={"days": 99}).status_code == 422


def test_changes_snapshot_is_reused(client, pg_conn):
    from lmi import web

    first = client.get("/api/changes", params={"days": 1}).json()
    n = pg_conn.execute("SELECT count(*), count(DISTINCT state) FROM mart.changes_snapshot").fetchone()
    assert n == (3, 1)                                   # jedno przeliczenie dało wszystkie trzy okresy
    pg_conn.execute("UPDATE mart.changes_snapshot SET data = data || '{\"marker\": 1}'")
    pg_conn.commit()
    assert client.get("/api/changes", params={"days": 30}).json()["marker"] == 1   # z zapisanych, bez liczenia
    assert first["daily"] and first["since"] == first["last_day"]
    web.refresh_changes(pg_conn)                          # wywołanie z porannego przebiegu
    assert "marker" not in client.get("/api/changes", params={"days": 7}).json()


def test_changes_show_only_complete_days(client, pg_conn, tmp_path):
    before = client.get("/api/changes", params={"days": 1}).json()
    # trwa poranny przebieg: jeden portal ma już nowy dzień, pozostałe jeszcze nie
    f = tmp_path / "o.csv"
    f.write_text("source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln\n"
                 "901,2026-06-29,9900011,Syntetyczna Rozwojowa,1000,500000\n"
                 "901,2026-07-06,9900011,Syntetyczna Rozwojowa,1000,500000\n")
    db.add_source(pg_conn, "otodom", "Otodom")
    db.approve_source(pg_conn, "otodom", "test", "pytest")
    db.import_csv(pg_conn, "otodom", f)
    run_id, _ = db.run_dedup(pg_conn)
    pg_conn.commit()
    after = client.get("/api/changes", params={"days": 1}).json()
    assert after["last_day"] == before["last_day"] == "2026-06-29"          # nie pół dnia
    assert after["daily"][-1]["active"] >= before["daily"][-1]["active"]   # liczba ofert nie spada w trakcie


def test_offer_links_freshest_listing_and_lowest_price(client, pg_conn, tmp_path):
    for src, price, pushed in (("otodom", 99000, ""), ("gratka", 88000, "2026-06-28")):
        f = tmp_path / f"{src}.csv"
        f.write_text("source_listing_id,observed_at,municipality_teryt,municipality_name,area_m2,price_pln,parcel_id,"
                     "url,pushed_up_at\n"
                     f"{src}1,2026-06-29,9900011,Syntetyczna Rozwojowa,842,{price},990001_1.0001.842,"
                     f"https://{src}.example/1,{pushed}\n")
        db.add_source(pg_conn, src, src)
        db.approve_source(pg_conn, src, "test", "pytest")
        db.import_csv(pg_conn, src, f)
    db.run_dedup(pg_conn)
    pg_conn.commit()
    rows = client.get("/api/municipality/9900011/offers", params={"min_area": 842, "max_area": 842}).json()
    o = next(r for r in rows if r["portals"] == 2)
    assert o["url"] == "https://gratka.example/1" and o["source"] == "gratka"   # podbita najpóźniej
    assert float(o["price"]) == 88000 and len(o["offers"]) == 2
    assert {x["source"] for x in o["offers"]} == {"otodom", "gratka"}


def test_offer_report_keeps_problem_and_links(client, monkeypatch):
    monkeypatch.setenv("LMI_ADMINS", "x")
    r = client.post("/api/feedback", json={"kind": "poprawka danych", "body": "Oferta: nieaktualna / archiwalna",
                                             "context": {"problem": "nieaktualna / archiwalna", "dzialka": "P-abc",
                                                         "ogloszenia": "https://a.example/1 | https://b.example/2"}})
    assert r.status_code == 200
    txt = client.get("/api/feedback/export", headers={"X-Auth-Request-User": "x"}).text
    assert "Problem z ofertą: nieaktualna / archiwalna" in txt and "ogłoszenie: https://b.example/2" in txt


def test_announcements_visible_for_four_business_days(client, pg_conn, monkeypatch):
    from datetime import date

    from lmi import web

    assert web.business_days_after(date(2026, 10, 16), 4) == date(2026, 10, 21)   # pt -> śr (bez weekendu)
    assert web.business_days_after(date(2026, 10, 19), 4) == date(2026, 10, 22)   # pn -> czw
    monkeypatch.setenv("LMI_ADMINS", "x")
    assert client.post("/api/announcements", json={"title": "Test"}).status_code == 403
    r = client.post("/api/announcements", headers={"X-Auth-Request-User": "x"},
                    json={"title": "Działa filtr: tylko od właścicieli", "body": "W ofertach gminy."})
    assert r.status_code == 200
    items = client.get("/api/announcements").json()
    assert [i["title"] for i in items] == ["Działa filtr: tylko od właścicieli"]
    pg_conn.execute("UPDATE app.announcements SET visible_until = current_date - 1")
    pg_conn.commit()
    assert client.get("/api/announcements").json() == []                         # po terminie znika sama
