#!/usr/bin/env python3
"""Zwiad: Rejestr Cen Nieruchomości (RCN) w geoportalu GUGiK — dane bezpłatne od 13.02.2026.

Usługa WFS: https://mapy.geoportal.gov.pl/wss/service/rcn
Wypisuje: warstwy usługi, ich pola, kilka przykładowych rekordów z małego obszaru
(Kąty Wrocławskie) i liczbę rekordów w całym województwie dolnośląskim.
Publiczny zakres RCN nie zawiera danych osobowych (strony transakcji nie są udostępniane).

Użycie na serwerze (bez przebudowy obrazu, ok. 10 zapytań):
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_rcn.py
Próbki działek z filtrem (powiat wrocławski, od 2024) i liczniki dla województwa:
    ... /scripts/probe_rcn.py --probki
"""
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

WFS = "https://mapy.geoportal.gov.pl/wss/service/rcn"
UA = "Mozilla/5.0 (X11; Linux x86_64) RadarDzialek/1.0 (zwiad RCN)"
# EPSG:4326 w WFS 2.0: kolejność szerokość, długość
SMALL = (50.95, 16.70, 51.05, 16.85)     # okolice Kątów Wrocławskich
REGION = (50.09, 14.81, 51.81, 17.80)    # województwo dolnośląskie (prostokąt)


def get(params: dict, timeout=90) -> tuple[int, bytes]:
    url = WFS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        body, status = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        print(f"  BŁĄD {type(e).__name__}: {e}")
        return 0, b""
    print(f"  {status} {len(body):>9}B {time.time() - t:5.1f}s {params.get('REQUEST')} {params.get('TYPENAMES', '')}")
    time.sleep(2)
    return status, body


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fes(teryt_prefix: str, since: str, extra: str = "") -> str:
    """Filtr FES 2.0: TERYT zaczyna się od prefiksu, data aktu od `since` (+ dodatkowy warunek)."""
    return ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:And>'
            '<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!"><fes:ValueReference>TERYT</fes:ValueReference>'
            f'<fes:Literal>{teryt_prefix}*</fes:Literal></fes:PropertyIsLike>'
            '<fes:PropertyIsGreaterThanOrEqualTo><fes:ValueReference>DOK_DATA</fes:ValueReference>'
            f'<fes:Literal>{since}</fes:Literal></fes:PropertyIsGreaterThanOrEqualTo>{extra}'
            '</fes:And></fes:Filter>')


def records(body: bytes) -> list[dict]:
    out = []
    for m in ET.fromstring(body).iter():
        if local(m.tag) in ("member", "featureMember"):
            obj = next(iter(m), None)
            if obj is not None:
                out.append({local(c.tag): (c.text or "").strip() for c in obj if len(c) == 0})
    return out


def probki() -> None:
    from collections import Counter

    print("### ms:dzialki: 300 rekordów z powiatu wrocławskiego (TERYT 0223*), akty od 2024-01-01")
    status, body = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "ms:dzialki",
                        "COUNT": "300", "FILTER": fes("0223", "2024-01-01")}, timeout=180)
    if status != 200:
        print(body[:800].decode("utf-8", "replace"))
        return
    try:
        rows = records(body)
    except ET.ParseError:
        print(body[:800].decode("utf-8", "replace"))
        return
    print(f"   rekordów: {len(rows)}")
    if not rows:
        print(body[:800].decode("utf-8", "replace"))
        return
    for f in ("TERYT", "TRAN_RODZAJ_TRANS", "TRAN_RODZAJ_RYNKU", "TRAN_SPRZEDAJACY", "TRAN_KUPUJACY",
              "NIER_RODZAJ", "NIER_PRAWO", "NIER_UDZIAL", "DZI_PRZEZN_WMPZP", "DZI_SPOSOB_UZYT", "DOK_TWORCA"):
        c = Counter((r.get(f) or "")[:40] for r in rows)
        print(f"   {f}: {c.most_common(10)}")
    def stats(f):
        v = sorted(float(r[f]) for r in rows if r.get(f) not in (None, ""))
        return f"n={len(v)} min={v[0]:.0f} mediana={v[len(v)//2]:.0f} max={v[-1]:.0f}" if v else "brak"
    for f in ("TRAN_CENA_BRUTTO", "NIER_CENA_BRUTTO", "DZI_CENA_BRUTTO", "NIER_POW_GRUNTU", "DZI_POW_EWID"):
        print(f"   {f}: {stats(f)}")
    tx = Counter(r.get("TRAN_LOKALNY_ID_IIP") for r in rows)
    print(f"   transakcji: {len(tx)}, działek na transakcję (max): {max(tx.values())}")
    print("   daty aktów:", min(r.get("DOK_DATA", "") for r in rows), "–", max(r.get("DOK_DATA", "") for r in rows))
    safe = ("TERYT", "TRAN_RODZAJ_TRANS", "TRAN_RODZAJ_RYNKU", "TRAN_CENA_BRUTTO", "DOK_DATA", "NIER_RODZAJ",
            "NIER_PRAWO", "NIER_POW_GRUNTU", "NIER_CENA_BRUTTO", "DZI_ID_DZIALKI", "DZI_PRZEZN_WMPZP", "DZI_POW_EWID",
            "DZI_SPOSOB_UZYT", "DZI_CENA_BRUTTO", "DZI_ADRES")
    for r in rows[:3]:
        print("   -", {k: r.get(k, "")[:50] for k in safe})

    print("\n### liczba rekordów działek w województwie (TERYT 02*) według roku aktu")
    for since, until in (("2023-01-01", "2024-01-01"), ("2024-01-01", "2025-01-01"), ("2025-01-01", "2026-01-01"),
                         ("2026-01-01", "2027-01-01")):
        extra = ('<fes:PropertyIsLessThan><fes:ValueReference>DOK_DATA</fes:ValueReference>'
                 f'<fes:Literal>{until}</fes:Literal></fes:PropertyIsLessThan>')
        status, body = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "ms:dzialki",
                            "RESULTTYPE": "hits", "FILTER": fes("02", since, extra)}, timeout=240)
        try:
            print(f"   {since[:4]}: {ET.fromstring(body).get('numberMatched')}")
        except ET.ParseError:
            print(f"   {since[:4]}: ", body[:300])
    print("\nKONIEC")


def luka(powiat: str, day: str) -> None:
    """Dlaczego usługa liczy rekordy, ale ich nie oddaje: ten sam dzień i powiat różnymi zapytaniami."""
    from datetime import date, timedelta

    d0 = date.fromisoformat(day)
    d1 = d0 + timedelta(days=1)
    when = ('<fes:PropertyIsGreaterThanOrEqualTo><fes:ValueReference>DOK_DATA</fes:ValueReference>'
            f'<fes:Literal>{d0}</fes:Literal></fes:PropertyIsGreaterThanOrEqualTo>'
            '<fes:PropertyIsLessThan><fes:ValueReference>DOK_DATA</fes:ValueReference>'
            f'<fes:Literal>{d1}</fes:Literal></fes:PropertyIsLessThan>')
    like = ('<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!"><fes:ValueReference>TERYT</fes:ValueReference>'
            f'<fes:Literal>{powiat}*</fes:Literal></fes:PropertyIsLike>')
    equal = f'<fes:PropertyIsEqualTo><fes:ValueReference>TERYT</fes:ValueReference><fes:Literal>{powiat}</fes:Literal></fes:PropertyIsEqualTo>'
    wrap = lambda inner: f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:And>{inner}</fes:And></fes:Filter>'
    variants = [
        ("TERYT LIKE + SORTBY + pola", {"FILTER": wrap(like + when), "SORTBY": "gid", "PROPERTYNAME": "TERYT,DOK_DATA,TRAN_LOKALNY_ID_IIP,SERWIS_RCN"}),
        ("TERYT LIKE, bez sortowania i pól", {"FILTER": wrap(like + when)}),
        ("TERYT =, bez sortowania", {"FILTER": wrap(equal + when)}),
        ("tylko data (całe województwo), bez sortowania", {"FILTER": wrap(when + '<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!"><fes:ValueReference>TERYT</fes:ValueReference><fes:Literal>02*</fes:Literal></fes:PropertyIsLike>')}),
    ]
    print(f"### luka: powiat {powiat}, dzień {d0}")
    for name, extra in variants:
        base = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "ms:dzialki"}
        _, hb = get({**base, "RESULTTYPE": "hits", "FILTER": extra["FILTER"]})
        try:
            hits = ET.fromstring(hb).get("numberMatched")
        except ET.ParseError:
            hits = hb[:120]
        status, body = get({**base, "COUNT": "1000", **extra}, timeout=180)
        try:
            recs = records(body)
            mine = [r for r in recs if (r.get("TERYT") or "").startswith(powiat)]
            serw = sorted({(r.get("SERWIS_RCN") or "")[:70] for r in mine})[:3]
            print(f"   {name}: usługa liczy {hits}, oddała {len(recs)} (z powiatu {powiat}: {len(mine)}), SERWIS_RCN: {serw}")
        except ET.ParseError:
            print(f"   {name}: usługa liczy {hits}, odpowiedź {status}: {body[:300]!r}")
    print("KONIEC")


def main() -> None:
    if "--luka" in sys.argv:
        i = sys.argv.index("--luka")
        luka(sys.argv[i + 1], sys.argv[i + 2])
        return
    if "--probki" in sys.argv:
        probki()
        return
    print("### GetCapabilities")
    status, body = get({"SERVICE": "WFS", "REQUEST": "GetCapabilities"})
    if status != 200:
        print(body[:600].decode("utf-8", "replace"))
        return
    root = ET.fromstring(body)
    versions = root.get("version")
    types = []
    for ft in root.iter():
        if local(ft.tag) == "FeatureType":
            name = next((c.text for c in ft if local(c.tag) == "Name"), None)
            title = next((c.text for c in ft if local(c.tag) == "Title"), "")
            crs = next((c.text for c in ft if local(c.tag) in ("DefaultCRS", "DefaultSRS")), "")
            types.append(name)
            print(f"  warstwa: {name} | {title} | {crs}")
    formats = sorted({e.text for e in root.iter() if local(e.tag) == "Value" and e.text and "/" in e.text})[:12]
    print(f"  wersja WFS: {versions}; formaty: {formats}")
    if not types:
        print("Brak warstw — wklej ten wynik do czatu.")
        return

    only = sys.argv[1:]
    for name in types:
        if only and name not in only:
            continue
        print(f"\n### {name}: pola")
        status, body = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "DescribeFeatureType", "TYPENAMES": name})
        if status == 200:
            try:
                fields = [(e.get("name"), (e.get("type") or "").split(":")[-1])
                          for e in ET.fromstring(body).iter() if local(e.tag) == "element" and e.get("type")]
                print("  ", fields[:60])
            except ET.ParseError:
                print("  ", body[:400])

        print(f"### {name}: przykłady (Kąty Wrocławskie)")
        status, body = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": name,
                            "COUNT": "3", "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
                            "BBOX": ",".join(map(str, SMALL)) + ",urn:ogc:def:crs:EPSG::4326"})
        if status == 200:
            try:
                fc = ET.fromstring(body)
                feats = [f for f in fc.iter() if local(f.tag) == "member" or local(f.tag) == "featureMember"]
                print(f"   rekordów w odpowiedzi: {len(feats)}")
                for m in feats[:3]:
                    obj = next(iter(m), None)
                    if obj is None:
                        continue
                    vals = []
                    for c in obj:
                        if len(c) == 0 and c.text and c.text.strip():
                            vals.append((local(c.tag), c.text.strip()[:50]))
                        elif len(c):
                            vals.append((local(c.tag), "<geometria/obiekt>"))
                    print("   -", vals[:40])
            except ET.ParseError:
                print("  ", body[:600].decode("utf-8", "replace"))
        else:
            print("  ", body[:600].decode("utf-8", "replace"))

        print(f"### {name}: liczba rekordów w dolnośląskim (prostokąt)")
        status, body = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": name,
                            "RESULTTYPE": "hits",
                            "BBOX": ",".join(map(str, REGION)) + ",urn:ogc:def:crs:EPSG::4326"}, timeout=180)
        if status == 200:
            try:
                r = ET.fromstring(body)
                print(f"   numberMatched={r.get('numberMatched')} numberOfFeatures={r.get('numberOfFeatures')}")
            except ET.ParseError:
                print("  ", body[:300])
        else:
            print("  ", body[:300].decode("utf-8", "replace"))
    print("\nKONIEC")


if __name__ == "__main__":
    main()
