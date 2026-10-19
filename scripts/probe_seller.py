#!/usr/bin/env python3
"""Zwiad: jak każdy portal oznacza ogłoszenie prywatne vs biuro (tylko KATEGORIA ogłoszeniodawcy).

Wypisuje wyłącznie nazwy pól i wartości typu tak/nie / krótkie kody (np. PRIVATE, agency, Person,
RealEstateAgent). Nazw biur, nazwisk, telefonów ani adresów nie wypisuje.
Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_seller.py
"""
import json
import os
import re
import time
import urllib.request

import psycopg

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
KEY = re.compile(r"private|agency|owner|seller|advertiser|offerer|business|developer|prywat|biuro|ogłoszeniodawc|"
                 r"userType|user_type|isCompany|company|offeredBy|agent", re.I)
SAFE_VALUE = re.compile(r"^(true|false|none|null|\d{1,3}|[A-Za-z_]{2,30})$")
TEXT = re.compile(r"(oferta prywatna|ogłoszenie prywatne|osoba prywatna|bezpośrednio od właściciela|"
                  r"ogłoszenie właściciela|biuro nieruchomości|agencja|pośrednik|deweloper)", re.I)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(6)
    return body


def walk(o, path="", out=None, depth=0):
    out = out if out is not None else []
    if depth > 9 or len(out) > 60:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}" if path else k
            if KEY.search(k) and not isinstance(v, (dict, list)):
                val = str(v)
                out.append((p, val if SAFE_VALUE.match(val) else f"<tekst {len(val)} zn.>"))
            if KEY.search(k) and isinstance(v, dict):
                out.append((p + ".@type", str(v.get("@type") or v.get("type") or "")[:30]))
            walk(v, p, out, depth + 1)
    elif isinstance(o, list):
        for v in o[:2]:
            walk(v, path + "[]", out, depth + 1)
    return out


def blobs(html):
    out = []
    for m in re.finditer(r'<script[^>]*(?:id="__NEXT_DATA__"|type="application/ld\+json")[^>]*>(.*?)</script>', html, re.S):
        try:
            out.append(json.loads(m.group(1), strict=False))
        except ValueError:
            pass
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            flat = json.loads(m.group(1))
            # Nuxt: płaska tablica; szukamy obiektów z kluczami o ogłoszeniodawcy
            for item in flat:
                if isinstance(item, dict) and any(KEY.search(k) for k in item):
                    out.append({k: (flat[v] if isinstance(v, int) and 0 <= v < len(flat) and not isinstance(flat[v], (dict, list)) else v)
                                for k, v in item.items() if KEY.search(k)})
        except ValueError:
            pass
    return out


def main():
    conn = psycopg.connect(os.environ.get("LMI_DATABASE_URL", "postgresql://lmi:lmi@db:5432/lmi"))
    print("### Otodom: pola w wynikach wyszukiwania (pierwsze 3 ogłoszenia)")
    html = get("https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/dolnoslaskie?limit=36&page=1")
    for b in blobs(html):
        items = (((b.get("props") or {}).get("pageProps") or {}).get("data") or {}).get("searchAds", {}).get("items") \
            if isinstance(b, dict) else None
        for it in (items or [])[:3]:
            print("   ", sorted(set(walk(it))))
    for source in ("otodom", "gratka", "nieruchomosci-online", "adresowo"):
        urls = [u for (u,) in conn.execute(
            """SELECT url FROM core.listing_observations WHERE source_id = %s AND url IS NOT NULL
               AND observed_at = (SELECT max(observed_at) FROM core.listing_observations WHERE source_id = %s)
               ORDER BY random() LIMIT 3""", (source, source))]
        print(f"\n### {source}: strony ofert")
        for url in urls:
            try:
                html = get(url)
            except Exception as exc:  # noqa: BLE001
                print(f"  {url[:80]}: błąd {exc}")
                continue
            fields = sorted({f for b in blobs(html) for f in walk(b)})[:25]
            text = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", html, flags=re.S)).split())
            marks = sorted({m.group(1).lower() for m in TEXT.finditer(text)})
            print(f"  {url.split('?')[0][:90]}")
            print(f"     pola: {fields}")
            print(f"     napisy na stronie: {marks}")
    print("\nKONIEC")


if __name__ == "__main__":
    main()
