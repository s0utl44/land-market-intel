#!/usr/bin/env python3
"""Zwiad portalu: czy wpuszcza serwer i jak wyglądają dane na stronie wyników z działkami.

Wypisuje WYŁĄCZNIE strukturę (nazwy pól, typy) oraz liczby z pól typu cena/metraż/współrzędne.
Teksty są zastępowane typem, więc wynik nie zawiera danych osobowych.

Użycie na serwerze (bez przebudowy obrazu):
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_portal.py gratka
Portale: gratka, morizon, nieruchomosci-online, adresowo
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
# kilka kandydatów na stronę "działki na sprzedaż, dolnośląskie"; bierzemy pierwszy działający
PORTALS = {
    "gratka": {
        "robots": "https://gratka.pl/robots.txt",
        "search": ["https://gratka.pl/nieruchomosci/dzialki-grunty/dolnoslaskie",
                   "https://gratka.pl/nieruchomosci/dzialki-grunty/sprzedaz/dolnoslaskie"],
    },
    "morizon": {
        "robots": "https://www.morizon.pl/robots.txt",
        "search": ["https://www.morizon.pl/dzialki/dolnoslaskie/",
                   "https://www.morizon.pl/dzialki/sprzedaz/dolnoslaskie/"],
    },
    "nieruchomosci-online": {
        "robots": "https://www.nieruchomosci-online.pl/robots.txt",
        "search": ["https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Dolno%C5%9Bl%C4%85skie",
                   "https://dolnoslaskie.nieruchomosci-online.pl/dzialki/"],
    },
    "adresowo": {
        "robots": "https://adresowo.pl/robots.txt",
        "search": ["https://adresowo.pl/dzialki/dolnoslaskie/",
                   "https://adresowo.pl/dzialki/"],
    },
}
NUMERIC_OK = re.compile(r"price|cena|amount|kwota|area|powierzch|surface|size|lat|lon|lng|total|count|page|limit|offset|value|id$", re.I)
SAFE_STR_KEYS = {"type", "currency", "__typename", "@type", "unit", "status", "category", "kind"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body, status, final = r.read().decode("utf-8", "replace"), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        body, status, final = e.read().decode("utf-8", "replace"), e.code, url
    except Exception as e:  # noqa: BLE001
        print(f"  BŁĄD {url}: {type(e).__name__}: {e}")
        return None, None, url
    print(f"  {status} {len(body):>8}B {time.time() - t:4.1f}s {final}")
    time.sleep(5)
    return status, body, final


def schema(v, key="", depth=0):
    if isinstance(v, dict):
        if depth >= 4:
            return f"{{…{len(v)} kluczy}}"
        return {k: schema(x, k, depth + 1) for k, x in list(v.items())[:50]}
    if isinstance(v, list):
        return "[]" if not v else [f"len={len(v)}", schema(v[0], key, depth + 1)]
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


def ad_lists(obj, path="$", out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            ad_lists(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        if len(obj) >= 3 and isinstance(obj[0], dict) and any(
            re.search(r"price|cena|area|powierzch|surface", k, re.I) for k in obj[0]
        ):
            out.append((path, len(obj)))
        for i, v in enumerate(obj[:3]):
            ad_lists(v, f"{path}[{i}]", out)
    return out


def get_path(obj, path):
    for part in re.findall(r"\.([^.\[]+)|\[(\d+)\]", path):
        obj = obj[part[0]] if part[0] else obj[int(part[1])]
    return obj


def nuxt_unflatten(data):
    """Rozpakowuje __NUXT_DATA__ (format devalue: płaska tablica, obiekty wskazują indeksy)."""
    memo = {}
    special = {-1: None, -2: None, -3: float("nan"), -4: float("inf"), -5: float("-inf"), -6: 0}

    def h(i, depth=0):
        if not isinstance(i, int):
            return i
        if i < 0:
            return special.get(i)
        if i in memo:
            return memo[i]
        if depth > 60:
            return "<głęboko>"
        v = data[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in (
                "Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef", "NuxtError"):
                out = h(v[1], depth + 1) if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in ("Date", "BigInt", "RegExp", "null"):
                out = v[1] if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in ("Set", "Map"):
                out = [h(x, depth + 1) for x in v[1:]]
            else:
                out = []
                memo[i] = out
                out.extend(h(x, depth + 1) for x in v)
                return out
        elif isinstance(v, dict):
            out = {}
            memo[i] = out
            for k, x in v.items():
                out[k] = h(x, depth + 1)
            return out
        else:
            out = v
        memo[i] = out
        return out

    return h(0)


def find_keys(obj, pattern, path="$", out=None, limit=25):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(pattern, k, re.I) and isinstance(v, (int, float, str)) and len(str(v)) < 30:
                out.append((f"{path}.{k}", v if not isinstance(v, str) or re.fullmatch(r"[\d.,-]+", v) else f"<str {len(v)}>"))
            find_keys(v, pattern, f"{path}.{k}", out, limit)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            find_keys(v, pattern, f"{path}[{i}]", out, limit)
    return out


def embedded_json(html):
    """Szuka JSON-ów osadzonych w stronie (Next.js, Nuxt, stan aplikacji, JSON-LD)."""
    found = []
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        found.append(("__NEXT_DATA__", m.group(1)))
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        found.append(("ld+json", m.group(1)))
    for m in re.finditer(r'<script[^>]*type="application/json"[^>]*id="([^"]+)"[^>]*>(.*?)</script>', html, re.S):
        found.append((f"json#{m.group(1)}", m.group(2)))
    for m in re.finditer(r"window\.(__[A-Z_]+__|[A-Za-z_]*[Ss]tate[A-Za-z_]*)\s*=\s*(\{.*?\});?\s*</script>", html, re.S):
        found.append((f"window.{m.group(1)}", m.group(2)))
    out = []
    for name, raw in found:
        try:
            data = json.loads(raw)
            if isinstance(data, str):
                data = json.loads(data)
            if name == "json#__NUXT_DATA__" and isinstance(data, list):
                data = nuxt_unflatten(data)
            out.append((name, data))
        except ValueError:
            out.append((name, None))
    return out


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "gratka"
    cfg = PORTALS[name]
    print(f"### {name}: robots.txt")
    _, body, _ = fetch(cfg["robots"])
    if body:
        rules = [l.strip() for l in body.splitlines() if l.lower().startswith(("disallow", "allow", "crawl-delay"))]
        hits = [r for r in rules if re.search(r"dzialk|grunt|szukaj|search|api|oferta|ogloszen|\?|crawl", r, re.I)]
        print(f"  reguł: {len(rules)}; istotne: {hits[:20]}")

    print(f"\n### {name}: wyniki wyszukiwania")
    for url in cfg["search"]:
        status, html, final = fetch(url)
        if status != 200 or not html:
            continue
        links = sorted(set(re.findall(r'href="([^"]*(?:oferta|ogloszenie|ofert|dzialka|/i/|\d{6,})[^"]*)"', html)))
        sample = [re.sub(r"[a-z-]{12,}", "…", l)[:90] for l in links[:3]]
        print(f"  linki wyglądające na oferty: {len(links)}, np. {sample}")
        counts = re.findall(r"(\d[\d\s\u00a0]{2,})\s*(?:ogłosze|ofert|wynik|działek)", html)[:5]
        print(f"  liczby ofert w tekście: {counts}")
        blobs = embedded_json(html)
        print(f"  osadzone JSON-y: {[(n, d is not None) for n, d in blobs]}")
        for n, data in blobs:
            if data is None:
                continue
            lists = ad_lists(data)
            if lists:
                print(f"\n  [{n}] listy ofert: {lists[:5]}")
                first = get_path(data, lists[0][0])[0]
                print(json.dumps(schema(first), ensure_ascii=False, indent=1)[:4000])
            elif n == "ld+json":
                print(f"\n  [{n}] {json.dumps(schema(data), ensure_ascii=False)[:1200]}")
        for n, data in blobs:
            if n == "json#__NUXT_DATA__" and data is not None:
                loc = find_keys(data, r"^(lat|lng|lon|latitude|longitude|teryt|gmina|commune|municipality|county|powiat|district|city|locality|province|region)$")
                pag = find_keys(data, r"^(page|pages|totalPages|total|totalCount|count|perPage|limit|offset)$", limit=12)
                print(f"\n  [{n}] współrzędne/lokalizacja: {loc}")
                print(f"  [{n}] paginacja: {pag}")
        if not any(ad_lists(d) for _, d in blobs if d is not None):
            # brak JSON-a: pokaż, jakie atrybuty data-* / klasy niosą cenę i metraż
            attrs = sorted(set(re.findall(r'(data-[a-z-]*(?:price|area|cena|size|id)[a-z-]*)=', html, re.I)))[:20]
            classes = sorted(set(re.findall(r'class="([^"]*(?:price|cena|area|powierzch|size)[^"]*)"', html, re.I)))[:15]
            print(f"  brak listy ofert w JSON; atrybuty: {attrs}\n  klasy: {classes}")
        if "--detale" in sys.argv:
            ids = re.findall(r'href="([^"]*/ob/\d+[^"]*)"', html) or [l for l in links if re.search(r"\d{6,}", l)]
            p2 = final + ("&" if "?" in final else "?") + "page=2"
            print(f"\n### {name}: strona 2 ({p2})")
            s2, h2, _ = fetch(p2)
            if h2:
                ids2 = re.findall(r'/ob/(\d+)', h2)
                ids1 = re.findall(r"/ob/(\d+)", html)
                print(f"  oferty na stronie 1: {ids1[:4]} | na stronie 2: {ids2[:4]}")
            if ids:
                detail = ids[0] if ids[0].startswith("http") else "https://" + final.split("/")[2] + ids[0]
                print(f"\n### {name}: strona oferty")
                ds, dh, _ = fetch(detail)
                if dh:
                    for n, data in embedded_json(dh):
                        if data is None:
                            continue
                        hits = find_keys(data, r"^(lat|lng|lon|latitude|longitude|teryt|gmina|commune|municipality|county|powiat|city|locality|addressLocality|postalCode|geo|price|area|powierzchnia|typ|type|rodzaj|przeznaczenie|plotType)$")
                        print(f"  [{n}] {hits}")
        break
    print("\nKONIEC")


if __name__ == "__main__":
    main()
