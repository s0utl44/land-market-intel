#!/usr/bin/env python3
"""Zwiad źródeł: sprawdza, jak wyglądają dane Otodom/OLX/ULDK widziane z tego serwera.

Wypisuje WYŁĄCZNIE strukturę (nazwy pól, typy) i wartości liczbowe pól typu cena/metraż/
współrzędne. Teksty (tytuły, opisy, nazwy sprzedających, telefony) są zastępowane typem,
więc wynik nie zawiera danych osobowych i można go bezpiecznie wkleić do czatu.

Uruchomienie (tylko biblioteka standardowa Pythona 3.9+):
    python3 probe_sources.py
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
NUMERIC_OK = re.compile(r"price|area|lat|lon|radius|zoom|total|page|count|limit|offset|size|value", re.I)
SAFE_STR_KEYS = {"key", "type", "currency", "__typename", "code", "unit", "status", "estate", "transaction"}
DEPTH = 4


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:  # noqa: BLE001
        print(f"  BŁĄD {url}: {type(e).__name__}: {e}")
        return None, None
    print(f"  {status} {len(body):>8}B {time.time() - t:4.1f}s {url}")
    time.sleep(3)  # grzecznie
    return status, body


def schema(v, key="", depth=0):
    """Struktura wartości bez treści tekstowych."""
    if isinstance(v, dict):
        if depth >= DEPTH:
            return f"{{…{len(v)} kluczy}}"
        return {k: schema(x, k, depth + 1) for k, x in list(v.items())[:60]}
    if isinstance(v, list):
        if not v:
            return "[]"
        return [f"len={len(v)}", schema(v[0], key, depth + 1)]
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v if NUMERIC_OK.search(key) else type(v).__name__
    if isinstance(v, str):
        if key in SAFE_STR_KEYS and len(v) <= 40:
            return v
        if re.fullmatch(r"-?\d+([.,]\d+)?", v.strip()) and NUMERIC_OK.search(key):
            return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ][\d:.+Z-]*)?", v):
            return "<data>"
        return f"<str {len(v)}>"
    return type(v).__name__


def show(title, obj):
    print(f"\n--- {title}")
    print(json.dumps(schema(obj), ensure_ascii=False, indent=1)[:6000])


def find_ad_lists(obj, path="$", out=None):
    """Szuka list obiektów wyglądających na ogłoszenia (mają id i cenę/metraż)."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            find_ad_lists(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and "id" in obj[0] and any(
            re.search(r"price|area|params", k, re.I) for k in obj[0]
        ):
            out.append((path, len(obj)))
        for i, v in enumerate(obj[:3]):
            find_ad_lists(v, f"{path}[{i}]", out)
    return out


def get_path(obj, path):
    for part in re.findall(r"\.([^.\[]+)|\[(\d+)\]", path):
        obj = obj[part[0]] if part[0] else obj[int(part[1])]
    return obj


def find_keys(obj, pattern, path="$", out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(pattern, k, re.I) and isinstance(v, (int, float, str)) and len(str(v)) < 20:
                out.append((f"{path}.{k}", v))
            find_keys(v, pattern, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:2]):
            find_keys(v, pattern, f"{path}[{i}]", out)
    return out


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    return json.loads(m.group(1)) if m else None


def olx_state(html):
    m = re.search(r"window\.__PRERENDERED_STATE__\s*=\s*(\".*?\");\s*\n", html or "", re.S)
    return json.loads(json.loads(m.group(1))) if m else None


def main():
    print(f"Python {sys.version.split()[0]}")
    print("\n### robots.txt")
    for name, url in (("otodom", "https://www.otodom.pl/robots.txt"), ("olx", "https://www.olx.pl/robots.txt")):
        _, body = fetch(url)
        if body:
            rules = [l.strip() for l in body.splitlines()
                     if l.lower().startswith(("disallow", "allow", "crawl-delay", "user-agent: *"))]
            hits = [r for r in rules if re.search(r"wyniki|oferta|dzialk|api|/d/|nieruchomosci", r, re.I)]
            print(f"  {name}: {len(rules)} reguł; istotne: {hits[:15]}")

    print("\n### OTODOM wyniki")
    _, html = fetch("https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/dolnoslaskie?limit=72&page=1")
    nd = next_data(html)
    print(f"  __NEXT_DATA__: {nd is not None}")
    slug = None
    if nd:
        lists = find_ad_lists(nd)
        print(f"  listy ogłoszeń: {lists}")
        print(f"  paginacja: {find_keys(nd, r'total|pages|itemsPerPage')[:12]}")
        if lists:
            items = get_path(nd, lists[0][0])
            show("otodom: pierwsze ogłoszenie z wyników", items[0])
            slug = items[0].get("slug")
    if slug:
        print("\n### OTODOM szczegóły")
        _, html = fetch(f"https://www.otodom.pl/pl/oferta/{slug}")
        nd = next_data(html)
        ad = (nd or {}).get("props", {}).get("pageProps", {}).get("ad")
        print(f"  pageProps.ad: {ad is not None}")
        if ad:
            print(f"  klucze ad: {sorted(ad.keys())}")
            show("otodom: ad.target", ad.get("target"))
            show("otodom: ad.location", ad.get("location"))
            show("otodom: ad.characteristics", ad.get("characteristics"))

    print("\n### OLX wyniki (HTML)")
    _, html = fetch("https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/dolnoslaskie/")
    st = olx_state(html)
    print(f"  __PRERENDERED_STATE__: {st is not None}")
    cat = reg = None
    if st:
        lists = find_ad_lists(st)
        print(f"  listy ogłoszeń: {lists}")
        print(f"  liczniki: {find_keys(st, r'total|pages|pageSize')[:12]}")
        ids = find_keys(st, r'^(categoryId|category_id|regionId|region_id)$')
        print(f"  ID kategorii/regionu: {ids[:12]}")
        cat = next((v for p, v in ids if "categ" in p.lower()), None)
        reg = next((v for p, v in ids if "region" in p.lower()), None)
        if lists:
            show("olx: pierwsze ogłoszenie z wyników", get_path(st, lists[0][0])[0])

    print("\n### OLX API")
    for off in (0, 960, 1000):
        _, body = fetch(f"https://www.olx.pl/api/v1/offers/?offset={off}&limit=40&category_id={cat}&region_id={reg}")
        try:
            data = json.loads(body or "")
        except ValueError:
            print("  (nie JSON)")
            continue
        print(f"  offset={off}: data={len(data.get('data', []))}, metadata={schema(data.get('metadata'))}, "
              f"links={list((data.get('links') or {}).keys())}")
        if off == 0 and data.get("data"):
            show("olx api: data[0]", data["data"][0])
            params = data["data"][0].get("params") or []
            print(f"  params keys: {[p.get('key') for p in params]}")

    print("\n### ULDK (GUGiK)")
    _, body = fetch("https://uldk.gugik.gov.pl/?request=GetCommuneByXY&xy=17.0385,51.1079,4326&result=teryt,name")
    print(f"  odpowiedź: {(body or '').strip()[:200]!r}")
    _, body = fetch("https://uldk.gugik.gov.pl/?request=GetParcelByXY&xy=17.0385,51.1079,4326&result=teryt")
    print(f"  działka: {(body or '').strip()[:200]!r}")
    print("\nKONIEC")


if __name__ == "__main__":
    main()
