#!/usr/bin/env python3
"""Zwiad portalu bez osadzonego JSON-a (oferty w samym HTML-u), np. nieruchomosci-online.

Wypisuje WYŁĄCZNIE strukturę: wzorce linków, szkielet kafelka oferty (znaczniki i klasy,
tekst zastąpiony długością, chyba że to liczba/cena/metraż), paginację i pola strony oferty.
Danych osobowych (nazwiska, telefony) nie wypisuje.

Użycie na serwerze (bez przebudowy obrazu):
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app \
        /scripts/probe_html.py "https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Dolno%C5%9Bl%C4%85skie"
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from html.parser import HTMLParser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
STATIC = re.compile(r"\.(css|js|png|jpe?g|webp|svg|gif|ico|woff2?)(\?|$)", re.I)
# tekst, który można pokazać: liczby, ceny, metraże, daty, krótkie etykiety z listy
NUMERIC_TEXT = re.compile(r"^[\d\s .,]+(zł|zl|PLN|m²|m2|ha|ar|%|/m²|zł/m²)?$", re.I)
SAFE_WORDS = re.compile(r"^(cena|powierzchnia|działka|dzialka|budowlana|rolna|rekreacyjna|leśna|inwestycyjna|"
                        r"usługowa|przemysłowa|siedliskowa|przeznaczenie|typ|rodzaj|gmina|powiat|"
                        r"zł|m²|ha|sprzedaż|dodano|aktualizacja|lokalizacja|wymiary|media|dojazd|"
                        r"brak|tak|nie|prąd|woda|gaz|kanalizacja|asfaltowy|utwardzony|polny)[:\s]*$", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body, status, final = r.read().decode("utf-8", "replace"), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        body, status, final = e.read().decode("utf-8", "replace"), e.code, url
    print(f"  {status} {len(body):>8}B {time.time() - t:4.1f}s {final}")
    time.sleep(5)
    return status, body, final


def safe_text(t):
    t = " ".join(t.split())
    if not t:
        return ""
    if NUMERIC_TEXT.match(t) or SAFE_WORDS.match(t) or re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{2}\.\d{4}", t):
        return t
    return f"<tekst {len(t)}>"


class Skeleton(HTMLParser):
    """Szkielet fragmentu HTML: znaczniki, klasy, atrybuty data-*, bezpieczny tekst."""
    KEEP = {"class", "href", "itemprop", "itemtype", "content", "id"}

    def __init__(self):
        super().__init__()
        self.out, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("img", "source", "svg", "path", "use", "br", "picture"):
            return
        parts = []
        for k, v in attrs:
            v = v or ""
            if k.startswith("data-") or k in self.KEEP:
                if k == "href":
                    v = re.sub(r"\d{5,}", "N", v)[:80]
                elif k == "content":
                    v = v if NUMERIC_TEXT.match(v.strip() or "x") else f"<{len(v)}>"
                elif k.startswith("data-") and not re.fullmatch(r"[\d.,-]*", v):
                    v = v[:30] if re.search(r"price|area|type|id|lat|lon|lng", k) else f"<{len(v)}>"
                parts.append(f'{k}="{v}"')
        self.out.append("  " * self.depth + f"<{tag} {' '.join(parts)}>".replace(" >", ">"))
        if tag not in ("meta", "input", "link", "hr"):
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in ("img", "source", "svg", "path", "use", "br", "picture", "meta", "input", "link", "hr"):
            return
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        t = safe_text(data)
        if t:
            self.out.append("  " * self.depth + t)


def skeleton(fragment, limit=6000):
    p = Skeleton()
    p.feed(fragment)
    return "\n".join(p.out)[:limit]


def element_at(html, start):
    """Wycina cały element HTML zaczynający się na pozycji `start` (proste liczenie znaczników)."""
    tag = re.match(r"<([a-zA-Z0-9]+)", html[start:]).group(1)
    depth, pos = 0, start
    pat = re.compile(rf"<(/?){tag}\b[^>]*?(/?)>", re.I)
    for m in pat.finditer(html, start):
        if m.group(2):
            continue
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:m.end()]
        pos = m.end()
    return html[start:pos + 4000]


def link_patterns(html):
    links = [l for l in re.findall(r'href="([^"#]+)"', html) if not STATIC.search(l)]
    pats = Counter(re.sub(r"[a-ząćęłńóśźż0-9-]{15,}", "…", re.sub(r"\d{5,}", "N", l))[:100] for l in links)
    return links, pats


def ld_json(html):
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return out


def numbers_only(v, key=""):
    if isinstance(v, dict):
        return {k: numbers_only(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [f"len={len(v)}"] + ([numbers_only(v[0], key)] if v else [])
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    s = str(v)
    if key in ("@type", "@context", "priceCurrency", "unitCode", "availability") or NUMERIC_TEXT.match(s.strip() or "x"):
        return s[:60]
    return f"<str {len(s)}>"


def main():
    url = sys.argv[1]
    print("### wyniki wyszukiwania")
    status, html, final = fetch(url)
    if status != 200:
        return
    for d in ld_json(html):
        print("  [ld+json]", json.dumps(numbers_only(d), ensure_ascii=False)[:1500])
    links, pats = link_patterns(html)
    print("\n  najczęstsze wzorce linków (cyfry 5+ -> N):")
    for p, n in pats.most_common(25):
        print(f"   {n:3d}  {p}")
    print("\n  paginacja:", sorted({re.sub(r'\d{5,}', 'N', l)[:120] for l in links
                                    if re.search(r"[?&,](p|page|strona|pn)=?\d", l)})[:8])
    counts = re.findall(r"(\d[\d\s ]{1,})\s*(?:ogłosze|ofert|wynik|działek)", html)[:6]
    print("  liczby ofert w tekście:", counts)

    # kafelek oferty: pierwszy element z data-id, który zawiera link do oferty
    tiles = [m.start() for m in re.finditer(r"<(li|div|article)\b[^>]*\bdata-id=\"\d+\"", html)]
    print(f"\n  elementy z data-id: {len(tiles)}")
    if tiles:
        el = element_at(html, tiles[0])
        print("\n### szkielet pierwszego kafelka\n" + skeleton(el))
    offer_links = [l for l in links if re.search(r"\d{6,}", l) and not re.search(r"[?&]", l)]
    if not offer_links:
        print("\nbrak linków do ofert\nKONIEC")
        return
    detail = offer_links[0] if offer_links[0].startswith("http") else "https://" + final.split("/")[2] + offer_links[0]
    print(f"\n### strona oferty ({len(offer_links)} linków z numerem)")
    s, dh, _ = fetch(detail)
    if s != 200:
        return
    for d in ld_json(dh):
        print("  [ld+json]", json.dumps(numbers_only(d), ensure_ascii=False)[:2500])
    coords = re.findall(r'["\']?(lat|lng|lon|latitude|longitude)["\']?\s*[:=]\s*["\']?(-?\d{1,3}\.\d+)', dh)[:8]
    print("  współrzędne w kodzie:", coords)
    attrs = sorted(set(re.findall(r'(data-[a-z-]*(?:lat|lon|lng|geo|map|price|area|teryt|gmina)[a-z-]*)="([^"]{0,40})"', dh, re.I)))[:15]
    print("  atrybuty data-*:", attrs)
    # pary "etykieta: wartość" z parametrów oferty (wartość pokazana tylko, jeśli bezpieczna)
    text = re.sub(r"<[^>]+>", "\n", dh)
    lines = [" ".join(t.split()) for t in text.splitlines() if t.strip()]
    print("  parametry:")
    for i, t in enumerate(lines):
        if re.fullmatch(r"(Cena|Powierzchnia|Przeznaczenie|Typ działki|Rodzaj działki|Lokalizacja|Gmina|Powiat|"
                        r"Wymiary|Dodano|Aktualizacja|Data dodania|Data aktualizacji|Media|Dojazd|Kształt)[^:]{0,20}:?", t):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            print(f"    {t} -> {safe_text(nxt)}")
    print("\nKONIEC")


if __name__ == "__main__":
    main()
