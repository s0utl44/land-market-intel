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
        a, b = re.findall(r"(\d{4}-\d{2}-\d{2})</fes:Literal>", flt)
        feats = [f for d, pw, f in self.feats if a <= d < b and pw.startswith(teryt)]
        if q.get("RESULTTYPE") == ["hits"]:
            return f'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="{len(feats)}"/>'
        start = int(q["STARTINDEX"][0])
        return collection(*feats[:self.cap]) if start == 0 else collection()


def test_capped_service_is_split_until_complete():
    feats = [(f"2025-01-{d:02d}", "0223", feature(f"T{d}{i}", f"022302_2.0001.{d}{i}", day=f"2025-01-{d:02d}", gid=d * 10 + i))
             for d in range(1, 29) for i in range(3)]
    svc = CappedService(feats, cap=4)
    rows, matched = rcn.fetch_period(svc.get, "02", date(2025, 1, 1), date(2025, 2, 1))
    assert matched == 84 and len(rows) == 84 and len({r[0] for r in rows}) == 84


def test_incomplete_download_is_refused():
    # jeden dzień i jeden powiat ponad limit: dalej dzielić się nie da
    feats = [("2025-01-05", "0223", feature(f"T{i}", f"022302_2.0001.{i}", day="2025-01-05", gid=i)) for i in range(6)]
    with pytest.raises(rcn.Incomplete):
        rcn.fetch_period(CappedService(feats, cap=4).get, "02", date(2025, 1, 5), date(2025, 1, 6))


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
    assert n == 7 and all("GEOMETRIA" not in c for c in calls)
    assert any("PropertyIsNull" in c for c in calls)                       # osobno akty bez daty
    log = pg_conn.execute("SELECT sum(matched), sum(saved) FROM scrape.rcn_fetch_log").fetchone()
    assert log == (7, 7)
    rows = pg_conn.execute("SELECT tx_id, ppm2, parcels, buildable FROM mart.rcn_land_transactions ORDER BY tx_id").fetchall()
    assert rows == [("LAND", 300, 1, True), ("LAND2", 250, 2, True)]
    # ponowne pobranie tych samych aktów niczego nie dubluje
    rcn.refresh(pg_conn, get, today=date(2025, 6, 10), since=date(2025, 5, 1))
    assert pg_conn.execute("SELECT count(*) FROM scrape.rcn_parcels").fetchone()[0] == 7
