#!/usr/bin/env python3
"""Zwiad: jakie dodatkowe informacje o ofercie pokazują strony ofert każdego portalu.

Bierze po 2 aktualne oferty z każdego portalu (z bazy) i wypisuje:
  - liczniki zainteresowania (odsłony, wyświetlenia, zapisy, obserwujący),
  - nazwy pól / parametrów oferty (media, dojazd, wymiary, MPZP, typ ogłoszeniodawcy...),
  - daty (dodania, aktualizacji) i ślady obniżek ceny.
Wartości tylko krótkie i bez ciągów cyfr wyglądających na telefon; nazwisk i kontaktów nie wypisuje.

Użycie na serwerze (bez przebudowy obrazu):
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_fields.py
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

import psycopg

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
COUNTERS = re.compile(r"(odsłon|wyświetle|wyswietle|obserwuj|zapisan|polubi|ulubion|viewsCount|viewCount|views"
                      r"|savedCount|favouritesCount|popularno)", re.I)
DATES = re.compile(r"(dodano|data dodania|aktualizacj|zaktualizowan|odświeżon|datePosted|dateModified|"
                   r"createdAt|modifiedAt|pushedUpAt|refreshedAt|addedAt)", re.I)
PRICE = re.compile(r"(obniż|obniz|stara cena|poprzednia cena|oldPrice|previousPrice|priceChange|do negocjacji|negocjac)", re.I)
SELLER = re.compile(r"(biuro nieruchomości|agencja|oferta prywatna|bezpośrednio|właściciel|deweloper|"
                    r"advertiserType|sellerType|isPrivateOwner|agency)", re.I)
PHONE = re.compile(r"\d[\d\s-]{7,}\d")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    finally:
        time.sleep(6)


def clean(s, n=90):
    s = PHONE.sub("<nr>", re.sub(r"<[^>]+>", " ", s))
    return " ".join(s.split())[:n]


def snippets(html, rx, width=70, limit=6):
    out = []
    for m in rx.finditer(html):
        frag = clean(html[max(0, m.start() - width):m.end() + width], 2 * width + 20)
        if frag and frag not in out:
            out.append(frag)
        if len(out) >= limit:
            break
    return out


def walk_keys(obj, path="", out=None, depth=0):
    """Ścieżki kluczy JSON z krótkimi wartościami (struktura, nie treść)."""
    out = out if out is not None else []
    if depth > 7 or len(out) > 400:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk_keys(v, f"{path}.{k}" if path else k, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:3]:
            walk_keys(v, path + "[]", out, depth + 1)
    else:
        v = obj if isinstance(obj, (int, float, bool)) or obj is None else clean(str(obj), 40)
        out.append((path, v))
    return out


def embedded_json(html):
    blobs = []
    for m in re.finditer(r'<script[^>]*(?:id="__NEXT_DATA__"|type="application/ld\+json")[^>]*>(.*?)</script>', html, re.S):
        try:
            blobs.append(json.loads(m.group(1), strict=False))
        except ValueError:
            pass
    return blobs


def labels(html):
    """Pary etykieta: wartość z HTML (dt/dd, th/td, 'Etykieta:' w spanach)."""
    pairs = re.findall(r"<(?:dt|th)[^>]*>(.*?)</(?:dt|th)>\s*<(?:dd|td)[^>]*>(.*?)</(?:dd|td)>", html, re.S)
    pairs += re.findall(r">\s*([A-ZŁŚŻŹĆ][\wąćęłńóśźż ]{2,30}):\s*</[^>]+>\s*<[^>]+>\s*([^<]{1,60})<", html)
    seen, out = set(), []
    for k, v in pairs:
        k = clean(k, 40)
        if k and k not in seen:
            seen.add(k)
            out.append(f"{k} = {clean(v, 50)}")
    return out[:60]


INTERESTING = re.compile(r"(characteristic|target|statist|view|count|price|date|created|modified|pushed|advert|agency|"
                         r"owner|seller|media|access|fence|location|plot|dimension|vicinity|additionalProperty|"
                         r"features|terrain|utilities|zoning)", re.I)


# dane kontaktowe i tożsamość ogłoszeniodawcy: nie wypisujemy nawet w zwiadzie
PERSONAL = re.compile(r"(name|phone|email|mail|contact|logo|image|photo|url|address|street|person|nip|licen)", re.I)


def main():
    conn = psycopg.connect(os.environ.get("LMI_DATABASE_URL", "postgresql://lmi:lmi@db:5432/lmi"))
    for source in ("otodom", "gratka", "nieruchomosci-online", "adresowo"):
        urls = [u for (u,) in conn.execute(
            """SELECT url FROM core.listing_observations WHERE source_id = %s AND url IS NOT NULL
               AND observed_at = (SELECT max(observed_at) FROM core.listing_observations WHERE source_id = %s)
               ORDER BY random() LIMIT 2""", (source, source))]
        print(f"\n######## {source}: {len(urls)} ofert")
        for url in urls:
            status, html = fetch(url)
            print(f"--- {status} {len(html)}B {url.split('?')[0][:90]}")
            if not html:
                continue
            for name, rx in (("LICZNIKI", COUNTERS), ("DATY", DATES), ("CENA/OBNIŻKI", PRICE), ("OGŁOSZENIODAWCA", SELLER)):
                found = snippets(html, rx)
                print(f"  [{name}] {len(found)}")
                for f in found:
                    print("     ·", f)
            keys = [(p, v) for b in embedded_json(html) for p, v in walk_keys(b) if INTERESTING.search(p) and not PERSONAL.search(p.split('.')[-1])]
            print(f"  [POLA JSON] {len(keys)}")
            for p, v in keys[:120]:
                print(f"     {p} = {v!r}")
            lab = labels(html)
            print(f"  [ETYKIETY HTML] {len(lab)}")
            for x in lab:
                print("     ", x)
    print("\nKONIEC")


if __name__ == "__main__":
    main()
