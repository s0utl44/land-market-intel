#!/usr/bin/env python3
"""Zwiad: Rejestr Cen Nieruchomości (RCN) w geoportalu GUGiK — dane bezpłatne od 13.02.2026.

Usługa WFS: https://mapy.geoportal.gov.pl/wss/service/rcn
Wypisuje: warstwy usługi, ich pola, kilka przykładowych rekordów z małego obszaru
(Kąty Wrocławskie) i liczbę rekordów w całym województwie dolnośląskim.
Publiczny zakres RCN nie zawiera danych osobowych (strony transakcji nie są udostępniane).

Użycie na serwerze (bez przebudowy obrazu, ok. 10 zapytań):
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_rcn.py
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


def main() -> None:
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
