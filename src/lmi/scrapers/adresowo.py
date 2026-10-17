"""Adresowo: działki na sprzedaż w województwie (dużo ogłoszeń bezpośrednio od właścicieli).

  - wyniki: https://adresowo.pl/dzialki/{kod regionu} (dolnośląskie: "fds"), 40 kafelków na stronę;
    kafelek <div data-offer-card data-id=...>: cena, powierzchnia (m² albo ha), link /o/...
  - strona oferty: JSON-LD Offer (cena) i Place (geo, opis)
Danych kontaktowych nie odczytujemy; z opisu bierzemy tylko rodzaj działki.
"""
from __future__ import annotations

import html as htmllib
import json
import logging
import re
from datetime import date

from .gratka import GratkaItem as Item, build_rows
from .http import FetchError
from .otodom import LayoutChanged, ScrapeStats, classify_land_use

log = logging.getLogger(__name__)

BASE = "https://adresowo.pl"
REGION_CODES = {"dolnoslaskie": "fds"}
MAX_PAGES = 300
UNITS = {"m²": 1.0, "m2": 1.0, "ha": 10_000.0, "a": 100.0, "ar": 100.0, "ary": 100.0, "arów": 100.0}


def list_path(region: str) -> str:
    return f"/dzialki/{REGION_CODES.get(region, region)}"


def search_url(region: str, page: int) -> str:
    return BASE + list_path(region) + ("" if page <= 1 else f"_l{page}")


def _number(text: str) -> float | None:
    s = re.sub(r"[\s ]", "", text or "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _cards(page_html: str) -> list[tuple[str, str]]:
    """(data-id, fragment HTML) dla każdego kafelka oferty."""
    starts = [(m.start(), m.group(1)) for m in re.finditer(r"<div\b[^>]*\bdata-offer-card\b[^>]*\bdata-id=\"(\d+)\"",
                                                           page_html)]
    return [(aid, page_html[pos:(starts[i + 1][0] if i + 1 < len(starts) else pos + 20_000)])
            for i, (pos, aid) in enumerate(starts)]


def parse_card(aid: str, frag: str) -> Item | None:
    href = re.search(r'href="(/o/[^"]+)"', frag)
    if not href:
        return None
    price = area = None
    # pary <span class="font-bold">129 000</span><span ...>zł</span>
    for value, unit in re.findall(r'<span class="font-bold">\s*([\d\s ,.]+?)\s*</span>\s*<span[^>]*>\s*([^<\s]+)\s*</span>',
                                  frag):
        unit = unit.strip().lower()
        if unit in ("zł", "zl", "pln") and price is None:
            price = _number(value)
        elif unit in UNITS and area is None and (n := _number(value)):
            area = round(n * UNITS[unit], 2)
    title = re.search(r'<h2\b[^>]*>(.*?)</h2>', frag, re.S)
    return Item(ad_id=aid, url=BASE + href.group(1), price_pln=price, area_m2=area, listed_at=None,
                refreshed_at=None, title=_text(title.group(1)) if title else None, description=None)


def parse_search_page(page_html: str, region: str = "dolnoslaskie") -> tuple[list[Item], int]:
    """Zwraca (ogłoszenia, najwyższy numer strony widoczny w stronicowaniu)."""
    cards = _cards(page_html)
    if not cards:
        raise LayoutChanged("adresowo: brak kafelków ofert")
    seen, items = set(), []
    for aid, frag in cards:
        if aid in seen:
            continue
        seen.add(aid)
        if (it := parse_card(aid, frag)) is not None:
            items.append(it)
    pages = [int(n) for n in re.findall(re.escape(list_path(region)) + r"_l(\d+)", page_html)]
    return items, max(pages, default=1)


def _ld_graph(page_html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page_html, re.S):
        try:
            data = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if isinstance(d, dict):
                out.extend(x for x in (d.get("@graph") or [d]) if isinstance(x, dict))
    return out


def _decimals(v) -> int:
    return len(str(v).split(".")[1]) if "." in str(v) else 0


def parse_detail_page(page_html: str, title: str | None = None, description: str | None = None) -> dict:
    graph = _ld_graph(page_html)
    place = next((g for g in graph if g.get("@type") == "Place" and g.get("geo")), None)
    if place is None:
        raise LayoutChanged("adresowo: brak Place/geo w JSON-LD")
    geo = place.get("geo") or {}
    lat, lon = geo.get("latitude"), geo.get("longitude")
    lat = float(lat) if lat not in (None, "") else None
    lon = float(lon) if lon not in (None, "") else None
    url = next((g.get("url") for g in graph if g.get("@type") == "Offer" and g.get("url")), "") or ""
    # adres oferty niesie rodzaj, np. /o/dzialka-budowlana-olawa-...
    land_use = classify_land_use(title) or classify_land_use(place.get("name")) or \
        classify_land_use(url.replace("-", " "))
    source = "tytuł"
    if land_use is None:
        land_use = classify_land_use(re.sub(r"<[^>]+>", " ", place.get("description") or description or ""))
        source = "opis"
    return {
        "lat": lat, "lon": lon,
        # pinezka działki ma 6+ miejsc po przecinku, środek miejscowości mniej (jak na Gratce)
        "precise": lat is not None and lon is not None and min(_decimals(geo.get("latitude")),
                                                                 _decimals(geo.get("longitude"))) >= 6,
        "land_use": land_use, "land_use_source": source if land_use else None,
        "area_m2": None,
        "municipality_hint": None,
    }


def scrape(get, cache, observed_at: date, region_slug: str = "dolnoslaskie", teryt_prefix: str = "02",
           max_details: int | None = None, max_pages: int = MAX_PAGES, geo_get=None) -> tuple[list[dict], ScrapeStats]:
    """Wszystkie strony wyników + brakujące strony ofert (raz na ofertę) + gminy z ULDK."""
    geo_get = geo_get or get
    stats = ScrapeStats()
    ads: dict[str, Item] = {}
    page, total_pages = 1, 1
    while page <= min(total_pages, max_pages):
        try:
            html = get(search_url(region_slug, page))
        except FetchError:
            if page == 1:
                raise
            log.warning("adresowo: strona %d niedostępna, kończę listę", page)
            break
        try:
            items, last_seen = parse_search_page(html, region_slug)
        except LayoutChanged:
            if page == 1:
                raise
            break  # strona za końcem listy bywa pusta
        total_pages = max(total_pages, last_seen)  # stronicowanie pokazuje tylko sąsiednie numery
        stats.pages += 1
        stats.items_seen += len(items)
        new = [it for it in items if it.ad_id not in ads]
        if not new:
            break  # pusta strona albo powtórka: koniec listy
        for it in new:
            ads[it.ad_id] = it
        page += 1
    stats.unique_ads = len(ads)
    log.info("adresowo: %d stron, %d unikalnych ogłoszeń", stats.pages, len(ads))
    rows = build_rows(ads.values(), get, cache, observed_at, teryt_prefix, max_details, geo_get, stats,
                      parse_detail_page, "adresowo")
    return rows, stats


def check(region_slug: str = "dolnoslaskie", details: int = 3) -> int:
    """Szybki test na żywej stronie: strony 1–2 wyników + kilka ofert + ULDK. Wypisuje tylko liczby."""
    from . import uldk
    from .http import PoliteClient

    client = PoliteClient()
    html = client.get(search_url(region_slug, 1))
    items, last = parse_search_page(html, region_slug)
    total = re.findall(r"(\d[\d\s ]{2,})\s*(?:ofert|ogłosze)", html)[:2]
    nav = sorted(set(re.findall(r'href="(' + re.escape(list_path(region_slug)) + r'[^"]+)"', html)))[:6]
    print(f"Wyniki: {len(items)} ofert na stronie 1, stronicowanie do: {last}, w tekście: {total}, linki stron: {nav}, "
          f"z ceną: {sum(1 for i in items if i.price_pln)}, z metrażem: {sum(1 for i in items if i.area_m2)}")
    items2, _ = parse_search_page(client.get(search_url(region_slug, 2)), region_slug)
    fresh = len({i.ad_id for i in items2} - {i.ad_id for i in items})
    print(f"Strona 2 ({search_url(region_slug, 2)}): {len(items2)} ofert, nowych względem strony 1: {fresh}")
    ok = bool(items) and fresh > 0 and sum(1 for i in items if i.price_pln and i.area_m2) >= 0.8 * len(items)
    for it in items[:details]:
        d = parse_detail_page(client.get(it.url), it.title)
        commune = None
        if d["lat"] is not None:
            commune = uldk.parse_commune_response(PoliteClient(min_delay=0.3, max_delay=0.6).get(
                uldk.commune_url(d["lat"], d["lon"])))
        print(f"  ad {it.ad_id}: cena={it.price_pln} m2={it.area_m2} lat={d['lat']} lon={d['lon']} "
              f"dokładna={d['precise']} typ={d['land_use']} ({d['land_use_source']}) gmina={commune}")
        ok = ok and d["lat"] is not None and commune is not None
    print("WYNIK:", "OK" if ok else "PROBLEM — wklej ten wynik do czatu")
    return 0 if ok else 1
