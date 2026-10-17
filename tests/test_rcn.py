import urllib.parse
from datetime import date

import pytest

from lmi import rcn


def feature(tx, parcel, nier="nieruchomoscGruntowaNiezabudowana", price="300000", area="1000", day="2025-05-10",
            share="1/1", tran="wolnyRynek", mpzp="budownictwoMieszkanioweJednorodzinne", gid=1):
    return f"""<wfs:member><ms:dzialki gml:id="dzialki.{gid}">
  <ms:TERYT>0223</ms:TERYT><ms:TRAN_LOKALNY_ID_IIP>{tx}</ms:TRAN_LOKALNY_ID_IIP>
  <ms:TRAN_RODZAJ_TRANS>{tran}</ms:TRAN_RODZAJ_TRANS><ms:TRAN_RODZAJ_RYNKU>rynekWtorny</ms:TRAN_RODZAJ_RYNKU>
  <ms:TRAN_SPRZEDAJACY>osobaFizyczna</ms:TRAN_SPRZEDAJACY><ms:TRAN_KUPUJACY>osobaFizyczna</ms:TRAN_KUPUJACY>
  <ms:TRAN_CENA_BRUTTO>{price}</ms:TRAN_CENA_BRUTTO>
  <ms:DOK_DATA><gml:TimeInstant gml:id="t{gid}"><gml:timePosition>{day}</gml:timePosition></gml:TimeInstant></ms:DOK_DATA>
  <ms:DOK_TWORCA>KOWALSKI JAN - NOTARIUSZ</ms:DOK_TWORCA>
  <ms:NIER_RODZAJ>{nier}</ms:NIER_RODZAJ><ms:NIER_UDZIAL>{share}</ms:NIER_UDZIAL>
  <ms:DZI_ID_DZIALKI>{parcel}</ms:DZI_ID_DZIALKI><ms:DZI_PRZEZN_WMPZP>{mpzp}</ms:DZI_PRZEZN_WMPZP>
  <ms:DZI_POW_EWID>{area}</ms:DZI_POW_EWID><ms:DZI_SPOSOB_UZYT>gruntyRolne</ms:DZI_SPOSOB_UZYT>
  <ms:DZI_ADRES>MSC:Domaszczyn;UL:Leśna;NR_PORZ:2D</ms:DZI_ADRES>
</ms:dzialki></wfs:member>"""


def collection(*features):
    return ('<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" '
            'xmlns:ms="http://mapserver.gis.umn.edu/mapserver">' + "".join(features) + "</wfs:FeatureCollection>")


def test_parse_and_row():
    recs = rcn.parse_features(collection(feature("T1", "022302_2.0012.401/2")))
    assert recs[0]["DOK_DATA"] == "2025-05-10" and recs[0]["TRAN_CENA_BRUTTO"] == "300000"
    row = rcn.to_row(recs[0])
    assert row[:4] == ("T1", "022302_2.0012.401/2", "0223022", date(2025, 5, 10))
    assert row[-1] == "Domaszczyn"                      # bez ulicy i numeru
    assert "KOWALSKI" not in repr(row)                  # notariusza nie zapisujemy


def test_helpers():
    assert rcn.gmina_teryt("022308_4.0001.806/3") == "0223084"
    assert rcn.gmina_teryt("bzdura") is None
    assert rcn.locality("UL:Leśna") is None
    assert list(rcn.months(date(2025, 11, 15), date(2026, 2, 1))) == [
        (date(2025, 11, 15), date(2025, 12, 1)), (date(2025, 12, 1), date(2026, 1, 1)), (date(2026, 1, 1), date(2026, 2, 1))]


class CappedService:
    """Fałszywa usługa, która przy dużym wyniku oddaje tylko pierwszą stronę (jak geoportal), dalej pusto."""

    def __init__(self, feats_by_day, cap=4):
        self.feats, self.cap, self.calls = feats_by_day, cap, 0

    def get(self, url):
        import re
        import urllib.parse
        self.calls += 1
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        flt = q["FILTER"][0]
        teryt = re.search(r"<fes:Literal>(\d+)\*</fes:Literal>", flt).group(1)
        days = re.findall(r"(\d{4}-\d{2}-\d{2})</fes:Literal>", flt)
        if not days:  # akty bez daty
            feats = []
        else:
            a, b = days
            feats = [f for d, pw, f in self.feats if a <= d < b and pw.startswith(teryt)]
        if q.get("RESULTTYPE") == ["hits"]:
            return f'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="{len(feats)}"/>'
        start = int(q["STARTINDEX"][0])
        return collection(*feats[:self.cap]) if start == 0 else collection()


def test_capped_service_is_split_until_complete():
    feats = [(f"2025-01-{d:02d}", "0223", feature(f"T{d}{i}", f"022302_2.0001.{d}{i}", day=f"2025-01-{d:02d}", gid=d * 10 + i))
             for d in range(1, 29) for i in range(3)]
    svc = CappedService(feats, cap=4)
    rows, matched, gaps = rcn.fetch_period(svc.get, "02", date(2025, 1, 1), date(2025, 2, 1))
    assert matched == 84 and len(rows) == 84 and len({r[0] for r in rows}) == 84 and gaps == []


def test_record_on_split_boundary_counted_twice_is_ok():
    feats = [(f"2025-01-{d:02d}", "0223", feature(f"T{d}{i}", f"022302_2.0001.{d}{i}", day=f"2025-01-{d:02d}", gid=d * 10 + i))
             for d in range(1, 29) for i in range(3)]

    class Overlapping(CappedService):
        def get(self, url):  # rekord z 2025-01-16 przychodzi także w pierwszej połowie (granica liczona dwa razy)
            body = super().get(url)
            if "STARTINDEX=0" in url and "2025-01-16" in urllib.parse.unquote(url) and "RESULTTYPE" not in url:
                extra = feats[15 * 3][2]
                body = body.replace("</wfs:FeatureCollection>", extra + "</wfs:FeatureCollection>")
            return body

    rows, matched, gaps = rcn.fetch_period(Overlapping(feats, cap=4).get, "02", date(2025, 1, 1), date(2025, 2, 1))
    assert matched == 84 and len(rows) == 84 and gaps == []          # powtórzenia usunięte przed zapisem


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(rcn, "_sleep", waits.append)
    return waits


def test_flaky_service_is_retried_before_gap(no_sleep):
    # geoportal pod obciążeniem oddaje pusto, a po chwili całość: to nie jest luka
    feats = [("2025-01-05", "0223", feature(f"T{i}", f"022302_2.0001.{i}", day="2025-01-05", gid=i)) for i in range(6)]

    class Flaky(CappedService):
        def get(self, url):
            if "RESULTTYPE" not in url and not no_sleep:
                return collection()
            return super().get(url)

    rows, matched, gaps = rcn.fetch_period(Flaky(feats, cap=10).get, "02", date(2025, 1, 5), date(2025, 1, 6))
    assert matched == 6 and len(rows) == 6 and gaps == [] and no_sleep == [20]


def test_parts_short_without_gaps_is_recorded_not_raised():
    feats = [("2025-01-05", "0223", feature(f"T{i}", f"022302_2.0001.{i}", day="2025-01-05", gid=i)) for i in range(6)]

    class Overcounting(CappedService):
        def get(self, url):  # całe województwo liczy o 1 więcej niż suma powiatów oddaje
            body = super().get(url)
            if "RESULTTYPE" in url and "02*" in urllib.parse.unquote(url):
                body = body.replace('numberMatched="6"', 'numberMatched="7"')
            return body

        # powiaty liczą razem 7 (0223 deklaruje 6 + 1 z 0201)
    svc = Overcounting(feats, cap=4)
    orig = svc.get

    def get(url):
        if "RESULTTYPE" in url and "0201*" in urllib.parse.unquote(url):
            return '<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="1"/>'
        return orig(url)

    rows, matched, gaps = rcn.fetch_period(get, "02", date(2025, 1, 5), date(2025, 1, 6))
    assert matched == 7 and len(rows) == 4 and gaps                     # bez wyjątku, luki zapisane


def test_service_gap_on_single_day_is_recorded_not_fatal():
    # jeden dzień i jeden powiat ponad to, co usługa oddaje: luka zapisana, reszta pobrana
    feats = [("2025-01-05", "0223", feature(f"T{i}", f"022302_2.0001.{i}", day="2025-01-05", gid=i)) for i in range(6)]
    rows, matched, gaps = rcn.fetch_period(CappedService(feats, cap=4).get, "02", date(2025, 1, 5), date(2025, 1, 6))
    assert matched == 6 and len(rows) == 4 and gaps == ["0223 2025-01-05–2025-01-06: brak 2 z 6"]


def test_service_error_is_raised():
    with pytest.raises(ValueError):
        rcn.parse_features('<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1"><ows:Exception>'
                           '<ows:ExceptionText>zły filtr</ows:ExceptionText></ows:Exception></ows:ExceptionReport>')


@pytest.mark.integration
def test_refresh_and_land_view(pg_conn):
    from lmi import db

    db.apply_schema(pg_conn)
    pages = {
        "2025-05": collection(
            feature("LAND", "022302_2.0001.1", price="300000", area="1000", gid=1),              # 300 zł/m²
            feature("LAND2", "022302_2.0001.2", price="250000", area="600", gid=2),
            feature("LAND2", "022302_2.0001.3", price="250000", area="400", gid=3),              # 2 działki: 250
            feature("MIX", "022302_2.0001.4", gid=4),
            feature("MIX", "022302_2.0001.5", nier="nieruchomoscGruntowaZabudowana", gid=5),     # dom + grunt
            feature("SHARE", "022302_2.0001.6", share="1/2", gid=6),                             # udział
            feature("BONUS", "022302_2.0001.7", tran="sprzedazZBonifikata", gid=7),              # bonifikata
        ),
    }
    calls = []
    page_size = 3  # serwer oddaje mniej niż PAGE: import musi stronicować po faktycznej liczbie

    def get(url):
        import re
        import urllib.parse
        calls.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        flt = q["FILTER"][0]
        m = re.search(r"GreaterThanOrEqualTo><fes:ValueReference>DOK_DATA</fes:ValueReference><fes:Literal>(\d{4}-\d{2})", flt)
        feats = re.findall(r"<wfs:member>.*?</wfs:member>", pages.get(m.group(1), collection()) if m else collection(), re.S)
        if q.get("RESULTTYPE") == ["hits"]:
            return f'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="{len(feats)}"/>'
        start = int(q["STARTINDEX"][0])
        return collection(*feats[start:start + page_size])

    n = rcn.refresh(pg_conn, get, today=date(2025, 6, 10), since=date(2025, 5, 1))
    assert rcn.repair(pg_conn, get) == (0, 0)
    assert n == 7 and all("GEOMETRIA" not in c for c in calls)
    assert any("PropertyIsNull" in c for c in calls)                       # osobno akty bez daty
    log = pg_conn.execute("SELECT sum(matched), sum(saved) FROM scrape.rcn_fetch_log").fetchone()
    assert log == (7, 7)
    rows = pg_conn.execute("SELECT tx_id, ppm2, parcels, buildable FROM mart.rcn_land_transactions ORDER BY tx_id").fetchall()
    assert rows == [("LAND", 300, 1, True), ("LAND2", 250, 2, True)]
    # ponowne pobranie tych samych aktów niczego nie dubluje
    rcn.refresh(pg_conn, get, today=date(2025, 6, 10), since=date(2025, 5, 1))
    assert pg_conn.execute("SELECT count(*) FROM scrape.rcn_parcels").fetchone()[0] == 7


@pytest.mark.integration
def test_repair_refetches_only_gaps(pg_conn):
    from lmi import db

    db.apply_schema(pg_conn)
    pg_conn.execute("DELETE FROM scrape.rcn_fetch_log")
    pg_conn.execute("DELETE FROM scrape.rcn_parcels")
    feats = [("2025-01-05", "0223", feature(f"T{i}", f"022302_2.0001.{i}", day="2025-01-05", gid=i)) for i in range(6)]
    # najpierw miesiąc pobrany z luką (usługa oddała 4 z 6), potem naprawa przy zdrowej usłudze
    rcn.refresh(pg_conn, CappedService(feats, cap=4).get, today=date(2025, 1, 20), since=date(2025, 1, 1))
    gaps = pg_conn.execute("SELECT gaps FROM scrape.rcn_fetch_log WHERE gaps IS NOT NULL").fetchall()
    assert gaps == [("0223 2025-01-05–2025-01-06: brak 2 z 6",)]
    svc = CappedService(feats, cap=10)
    assert rcn.repair(pg_conn, svc.get) == (1, 0)
    assert svc.calls <= 4                                               # tylko ten jeden dzień i powiat
    assert pg_conn.execute("SELECT count(*) FROM scrape.rcn_parcels").fetchone()[0] == 6
    assert pg_conn.execute("SELECT saved, gaps FROM scrape.rcn_fetch_log WHERE period_start = '2025-01-01'").fetchone() == (6, None)


def test_duplicate_records_in_service_are_not_a_gap(no_sleep):
    # RCN ma dwa identyczne wpisy tej samej działki w akcie: usługa liczy 3, po usunięciu powtórzeń są 2
    feats = [("2025-01-05", "0223", feature("T1", "022302_2.0001.1", day="2025-01-05", gid=1)),
             ("2025-01-05", "0223", feature("T1", "022302_2.0001.1", day="2025-01-05", gid=2)),
             ("2025-01-05", "0223", feature("T2", "022302_2.0001.2", day="2025-01-05", gid=3))]
    rows, matched, gaps = rcn.fetch_period(CappedService(feats, cap=10).get, "02", date(2025, 1, 5), date(2025, 1, 6))
    assert matched == 3 and len(rows) == 2 and gaps == [] and no_sleep == []


@pytest.mark.integration
def test_undated_query_rejected_by_service_is_noted_not_fatal(pg_conn):
    import urllib.error

    from lmi import db

    db.apply_schema(pg_conn)
    pg_conn.execute("DELETE FROM scrape.rcn_fetch_log")
    feats = [("2025-01-05", "0223", feature("T1", "022302_2.0001.1", day="2025-01-05", gid=1))]
    svc = CappedService(feats, cap=10)

    def get(url):
        if "PropertyIsNull" in urllib.parse.unquote(url):
            raise urllib.error.HTTPError(url, 403, "Server processing failed", {}, None)
        return svc.get(url)

    assert rcn.refresh(pg_conn, get, today=date(2025, 1, 20), since=date(2025, 1, 1)) == 1
    noted = pg_conn.execute("SELECT gaps FROM scrape.rcn_fetch_log WHERE period_start IS NULL").fetchone()[0]
    assert noted.startswith("akty bez daty")
    assert rcn.repair(pg_conn, get) == (0, 1)        # takiej uwagi naprawa nie ponawia w kółko
