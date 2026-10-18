#!/usr/bin/env python3
"""Zwiad: jak Nieruchomości-online oznacza ogłoszenia archiwalne (na liście i na stronie oferty).

Pobiera kilka stron listy województwa (tylko ?p=N, zgodnie z robots.txt) i po 3 oferty z każdej,
wypisuje pola JSON-LD (bez danych kontaktowych) i czy strona oferty ma pasek "Ogłoszenie archiwalne".
Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_archived.py
"""
import json
import re
import time
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
LIST = "https://dolnoslaskie.nieruchomosci-online.pl/dzialki,sprzedaz/"
ARCHIVED_AD = "https://wojciechowice.nieruchomosci-online.pl/dzialka,w-gorach/26078349.html"
PERSONAL = re.compile(r"name|telephone|email|agent|seller|author|image|logo", re.I)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(6)
    return body


def ld(html):
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


def keys(obj, prefix="", out=None, depth=0):
    out = out if out is not None else {}
    if depth > 5:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if PERSONAL.search(k) and k not in ("@type",):
                continue
            keys(v, f"{prefix}.{k}" if prefix else k, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:2]:
            keys(v, prefix + "[]", out, depth + 1)
    else:
        out.setdefault(prefix, str(obj)[:60])
    return out


def marks(html):
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    return {
        "archiwalne_pasek": bool(re.search(r">\s*Ogłoszenie archiwalne\s*<", html)),
        "slowo_archiw": len(re.findall(r"archiwal", text, re.I)),
        "nieaktualne": len(re.findall(r"nieaktualn|wygasł|zakończon", text, re.I)),
    }


def offers_of(html):
    for b in ld(html):
        if isinstance(b, dict) and b.get("@type") == "CollectionPage":
            offers = (b.get("mainEntity") or {}).get("offers") or []
            agg = offers[0] if isinstance(offers, list) and offers else offers
            return (agg or {}).get("offers") or []
    return []


print("### oferta archiwalna (przykład od użytkownika)")
h = get(ARCHIVED_AD)
print("  znaczniki:", marks(h))
for b in ld(h):
    if isinstance(b, dict) and b.get("@type") in ("RealEstateListing", "Offer", "Product"):
        for k, v in keys(b).items():
            if re.search(r"avail|valid|date|status|expir|offer", k, re.I):
                print(f"    {b.get('@type')}.{k} = {v}")

for page in (1, 100, 250, 400, 450):
    try:
        html = get(LIST + ("" if page == 1 else f"?p={page}"))
    except Exception as exc:  # noqa: BLE001
        print(f"### strona {page}: błąd {exc}")
        continue
    offers = offers_of(html)
    print(f"### strona {page}: {len(offers)} ofert w JSON-LD, znaczniki listy: {marks(html)}")
    if offers:
        print("  pola oferty na liście:", sorted(keys(offers[0]).keys()))
    for o in offers[:3]:
        try:
            d = get(o.get("url"))
        except Exception as exc:  # noqa: BLE001
            print(f"    {o.get('url')}: błąd {exc}")
            continue
        listing = next((b for b in ld(d) if isinstance(b, dict) and b.get("@type") == "RealEstateListing"), {})
        print(f"    {o.get('url')}: {marks(d)} datePosted={listing.get('datePosted')} "
              f"dateModified={listing.get('dateModified')} availability={(listing.get('offers') or {}).get('availability') if isinstance(listing.get('offers'), dict) else None}")
print("KONIEC")
