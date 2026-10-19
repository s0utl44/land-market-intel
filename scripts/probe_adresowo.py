#!/usr/bin/env python3
"""Zwiad: gdzie na stronie oferty Adresowo jest oznaczenie właściciel / biuro (po backfillu ~90% "prywatny",
a inne portale przy tych samych działkach często pokazują biuro).

Dla ofert zapisanych jako "prywatny", które inny portal pokazuje jako biuro, oraz dla kilku "biuro" wypisuje każde
wystąpienie napisów o ogłoszeniodawcy z klasą elementu, w którym stoi, i krótkim kontekstem (cyfry wycięte).
Pola JSON-LD o ogłoszeniodawcy: tylko @type. Nazw biur, nazwisk ani telefonów nie wypisuje.
Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_adresowo.py
"""
import json
import os
import re
import time
import urllib.request

import psycopg

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
PHRASES = re.compile(r"właściciel\w*|bez pośrednik\w*|bezpośrednio|biur\w* nieruchomości|pośrednik\w*|agencj\w*|"
                     r"licencj\w*|prowizj\w*|ogłoszeniodawc\w*|osoba prywatna|prywatn\w*", re.I)
WORDS = re.compile(r"[A-ZŁŚŻŹĆŃÓ][a-ząęłńóśżźć]+(?:\s+[A-ZŁŚŻŹĆŃÓ][a-ząęłńóśżźć]+)+")  # nazwy własne


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(6)
    return body


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\d", "#", s)
    s = WORDS.sub("<nazwa>", s)
    return " ".join(s.split())


def enclosing_class(html, pos):
    for m in reversed(list(re.finditer(r'<(\w+)[^>]*?class="([^"]*)"', html[max(0, pos - 3000):pos]))):
        return f"{m.group(1)}.{m.group(2)[:60]}"
    return "?"


def main():
    conn = psycopg.connect(os.environ.get("LMI_DATABASE_URL", "postgresql://lmi:lmi@db:5432/lmi"))
    rows = conn.execute("""
        WITH links AS (SELECT source_id, source_listing_id, property_key FROM core.listing_property_links
                       WHERE run_id = (SELECT max(run_id) FROM core.dedup_runs)),
        s AS (SELECT l.property_key, l.source_id, o.url,
                     coalesce(od.detail->'features'->>'seller', od.detail->>'list_seller',
                              pd.detail->'features'->>'seller') AS seller
              FROM links l
              JOIN core.listing_observations o ON o.source_id = l.source_id AND o.source_listing_id = l.source_listing_id
               AND o.observed_at = (SELECT max(observed_at) FROM core.listing_observations x WHERE x.source_id = l.source_id)
              LEFT JOIN scrape.otodom_details od ON l.source_id = 'otodom' AND od.ad_id = l.source_listing_id
              LEFT JOIN scrape.portal_details pd ON pd.source_id = l.source_id AND pd.ad_id = l.source_listing_id)
        (SELECT DISTINCT ON (a.url) 'prywatny, inny portal: biuro' AS kind, a.url FROM s a
           JOIN s b ON a.property_key = b.property_key AND b.source_id <> 'adresowo' AND b.seller = 'biuro'
          WHERE a.source_id = 'adresowo' AND a.seller = 'prywatny' ORDER BY a.url LIMIT 4)
        UNION ALL
        (SELECT DISTINCT ON (a.url) 'prywatny, inny portal: prywatny', a.url FROM s a
           JOIN s b ON a.property_key = b.property_key AND b.source_id <> 'adresowo' AND b.seller = 'prywatny'
          WHERE a.source_id = 'adresowo' AND a.seller = 'prywatny' ORDER BY a.url LIMIT 3)
        UNION ALL
        (SELECT 'biuro', url FROM s WHERE source_id = 'adresowo' AND seller = 'biuro' LIMIT 3)""").fetchall()
    for kind, url in rows:
        try:
            html = get(url)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{kind}] {url}\n   błąd: {exc}")
            continue
        body = re.sub(r"<script.*?</script>|<style.*?</style>", lambda m: " " * len(m.group(0)), html, flags=re.S)
        print(f"\n[{kind}] {url}")
        for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(b, strict=False)
            except ValueError:
                continue
            for g in (d.get("@graph") or [d]) if isinstance(d, dict) else d:
                if isinstance(g, dict):
                    for k in ("seller", "offeredBy", "agent", "author", "provider"):
                        v = g.get(k) or (g.get("offers") or {}).get(k) if isinstance(g.get("offers"), dict) else g.get(k)
                        if isinstance(v, dict):
                            print(f"   JSON-LD {g.get('@type')}.{k}.@type = {v.get('@type')}")
        seen = set()
        for m in PHRASES.finditer(body):
            cls = enclosing_class(body, m.start())
            ctx = clean(body[max(0, m.start() - 120):m.end() + 80])[-110:]
            key = (cls, m.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            print(f"   [{cls}] …{ctx}…")
    print("\nKONIEC")


if __name__ == "__main__":
    main()
