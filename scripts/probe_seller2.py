#!/usr/bin/env python3
"""Zwiad 2: skąd wziąć typ ogłoszeniodawcy na Gratce i Nieruchomościach-online (po backfillu prawie 100% "biuro").

Dla kilku aktywnych ofert każdego z tych portali (część zapisanych jako "biuro", część jako "prywatny") pobiera
stronę i wypisuje: zapisany typ, @type ogłoszeniodawcy z JSON-LD, pola tak/nie i krótkie kody o ogłoszeniodawcy
z danych strony oraz napisy typu "oferta prywatna" / "biuro nieruchomości". Nazw, nazwisk ani telefonów nie wypisuje.
Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_seller2.py
"""
import json
import os
import re
import time
import urllib.request

import psycopg

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
KEY = re.compile(r"private|prywat|agency|agent|advertiser|owner|seller|offeredBy|business|company|developer|"
                 r"userType|user_type|isCompany|ownerType|accountType|sellerType", re.I)
SAFE = re.compile(r"^(true|false|none|null|\d{1,3}|[A-Za-z_\-]{2,30})$")
TEXT = re.compile(r"(oferta prywatna|ogłoszenie prywatne|osoba prywatna|prywatny sprzedający|od właściciela|"
                  r"bezpośrednio|bez pośrednik|biuro nieruchomości|agencja nieruchomości|pośrednik|deweloper|"
                  r"numer licencji|oferta biura|ogłoszeniodawca)", re.I)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(6)
    return body


def walk(o, path="", out=None, depth=0):
    out = out if out is not None else set()
    if depth > 10 or len(out) > 40:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}" if path else k
            if KEY.search(k):
                if isinstance(v, dict):
                    out.add((p + ".@type", str(v.get("@type") or v.get("type") or "")[:30]))
                elif not isinstance(v, list):
                    val = str(v)
                    out.add((p, val if SAFE.match(val) else f"<tekst {len(val)} zn.>"))
            walk(v, p, out, depth + 1)
    elif isinstance(o, list):
        for v in o[:3]:
            walk(v, path + "[]", out, depth + 1)
    return out


def blobs(html):
    out = []
    for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', html, re.S):
        try:
            out.append(json.loads(m.group(1), strict=False))
        except ValueError:
            pass
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            flat = json.loads(m.group(1))
            for item in flat:
                if isinstance(item, dict) and any(KEY.search(k) for k in item):
                    out.append({k: (flat[v] if isinstance(v, int) and 0 <= v < len(flat)
                                    and not isinstance(flat[v], (dict, list)) else v)
                                for k, v in item.items() if KEY.search(k)})
        except ValueError:
            pass
    return out


def main():
    conn = psycopg.connect(os.environ.get("LMI_DATABASE_URL", "postgresql://lmi:lmi@db:5432/lmi"))
    for source in ("gratka", "nieruchomosci-online"):
        rows = conn.execute("""
            SELECT seller, url FROM (
              SELECT d.detail->'features'->>'seller' AS seller, o.url,
                     row_number() OVER (PARTITION BY d.detail->'features'->>'seller' ORDER BY random()) rn
              FROM core.listing_observations o
              JOIN scrape.portal_details d ON d.source_id = o.source_id AND d.ad_id = o.source_listing_id
              WHERE o.source_id = %(s)s AND o.url IS NOT NULL
                AND o.observed_at = (SELECT max(observed_at) FROM core.listing_observations WHERE source_id = %(s)s)
            ) x WHERE rn <= 4""", {"s": source}).fetchall()
        print(f"\n######## {source}")
        for seller, url in rows:
            try:
                html = get(url)
            except Exception as exc:  # noqa: BLE001
                print(f"\n[{seller}] {url}\n   błąd: {exc}")
                continue
            text = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", html, flags=re.S)).split())
            marks = sorted({m.group(1).lower() for m in TEXT.finditer(text)})
            fields = sorted({f for b in blobs(html) for f in walk(b)})[:30]
            print(f"\n[zapisane: {seller}] {url}")
            print(f"   pola: {fields}")
            print(f"   napisy: {marks}")
    print("\nKONIEC")


if __name__ == "__main__":
    main()
