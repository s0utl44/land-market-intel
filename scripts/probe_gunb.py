#!/usr/bin/env python3
"""Zwiad: skąd pobrać rejestr pozwoleń na budowę GUNB (RWDZ) i jakie ma kolumny.

Sprawdza katalog otwartych danych (dane.gov.pl) i stronę pobierania wyszukiwarki GUNB. Z plików czyta
tylko nagłówek i kilka wartości kolumn opisowych (kategoria, rodzaj, data, gmina). Nazw inwestorów
(dane osobowe) nie wypisuje.
Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_gunb.py
"""
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
PERSONAL = re.compile(r"inwestor|nazwa|imie|imię|nazwisk|pesel|adres_inw|wnioskodawc", re.I)


def get(url, limit=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read(limit) if limit else r.read()
        info = (r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length"))
    time.sleep(3)
    return data, info


def show_csv(raw: bytes, label: str):
    for enc in ("utf-8-sig", "cp1250", "iso-8859-2"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:200000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
    if not rows:
        print(f"   {label}: pusty")
        return
    head = rows[0]
    print(f"   {label}: kolumny ({len(head)}): {head}")
    for i, col in enumerate(head):
        if PERSONAL.search(col):
            continue
        vals = sorted({r[i] for r in rows[1:200] if len(r) > i and r[i]})[:6]
        print(f"      {col}: {[v[:40] for v in vals]}")


print("### dane.gov.pl: zbiory o pozwoleniach na budowę")
for q in ("pozwolenia na budowę", "RWDZ", "rejestr wniosków decyzji GUNB"):
    try:
        data, _ = get("https://api.dane.gov.pl/1.4/search?q=" + urllib.parse.quote(q) + "&per_page=10")
        js = json.loads(data)
        for item in js.get("data", [])[:10]:
            a = item.get("attributes", {})
            print(f"  [{item.get('type')}] {item.get('id')}: {a.get('title', '')[:100]} | {a.get('url') or ''}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {q}: błąd {exc}")

print("\n### wyszukiwarka GUNB: strona pobierania")
for url in ("https://wyszukiwarka.gunb.gov.pl/pobranie.html", "https://wyszukiwarka.gunb.gov.pl/"):
    try:
        data, info = get(url)
        html = data.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'href="([^"]+\.(?:zip|csv|xlsx?)[^"]*)"', html, re.I)))
        print(f"  {url}: {info[0]}, linki do plików: {len(links)}")
        for l in links[:40]:
            print("     ", l)
    except Exception as exc:  # noqa: BLE001
        print(f"  {url}: błąd {exc}")

print("\n### próba: plik dla dolnośląskiego (nagłówek)")
candidates = [
    "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_dolnoslaskie.zip",
    "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_dolnoslaskie.csv",
]
for url in candidates:
    try:
        data, info = get(url)
        print(f"  {url}: {info}")
        if data[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(data))
            for name in z.namelist()[:5]:
                print(f"    w archiwum: {name} ({z.getinfo(name).file_size} B)")
                with z.open(name) as f:
                    show_csv(f.read(300000), name)
        else:
            show_csv(data[:300000], url.rsplit("/", 1)[-1])
    except urllib.error.HTTPError as exc:
        print(f"  {url}: HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {url}: błąd {exc}")
print("KONIEC")
