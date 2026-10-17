"""Nieruchomości-online: działki na sprzedaż w województwie.

Dane ze schema.org (JSON-LD) osadzonego w stronach:
  - wyniki: https://{region}.nieruchomosci-online.pl/dzialki,sprzedaz/?p=N
    CollectionPage.mainEntity.offers[0] (AggregateOffer).offers: cena, metraż, adres oferty
  - strona oferty: RealEstateListing (geo, datePosted, additionalProperty)
Wyszukiwarka nie obsługuje całego województwa, ale powyższa strona regionu tak.
robots.txt zabrania ?o=, ?c, ?op, ?pn i ?secCode; używamy tylko ?p=N. Danych kontaktowych
(agent, telefon) nie odczytujemy.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from . import features
from .gratka import GratkaItem as Item, _date, _num, build_rows
from .http import FetchError
from .otodom import LayoutChanged, ScrapeStats, classify_land_use

log = logging.getLogger(__name__)

LIST_URL = "https://{region}.nieruchomosci-online.pl/dzialki,sprzedaz/"
MAX_PAGES = 400


def _decimals(v) -> int:
    return len(str(v).split(".")[1]) if "." in str(v) else 0


def search_url(region: str, page: int) -> str:
    return LIST_URL.format(region=region) + ("" if page <= 1 else f"?p={page}")


def ld_json(html: str) -> list:
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        out.extend(data if isinstance(data, list) else [data])
    return out


def _of_type(blobs: list, type_name: str) -> dict | None:
    return next((b for b in blobs if isinstance(b, dict) and b.get("@type") == type_name), None)


def ad_id(url: str) -> str | None:
    m = re.search(r"/(\d{5,})\.html", url or "")
    return m.group(1) if m else None


def parse_search_page(html: str) -> tuple[list[Item], int]:
    """Zwraca (ogłoszenia, najwyższy numer strony widoczny w stronicowaniu)."""
    page = _of_type(ld_json(html), "CollectionPage")
    if page is None:
        raise LayoutChanged("nieruchomosci-online: brak CollectionPage w JSON-LD")
    offers = (page.get("mainEntity") or {}).get("offers") or []
    agg = offers[0] if isinstance(offers, list) and offers else offers
    items = []
    for o in (agg or {}).get("offers") or []:
        url = o.get("url") or ""
        if not (aid := ad_id(url)):
            continue
        place = o.get("itemOffered") or {}
        items.append(Item(
            ad_id=aid, url=url, price_pln=_num(o.get("price")), area_m2=_num(place.get("floorSize")),
            listed_at=None, refreshed_at=None, title=o.get("name"), description=place.get("description"),
        ))
    pages = [int(n) for n in re.findall(r"dzialki,sprzedaz/\?p=(\d+)", html)]
    return items, max(pages, default=1)


def _land_use_from_props(listing: dict) -> str | None:
    for p in listing.get("additionalProperty") or []:
        if isinstance(p, dict) and re.search(r"rodzaj|przeznacz|typ", str(p.get("name") or ""), re.I):
            if (lu := classify_land_use(str(p.get("value") or ""))):
                return lu
    return None


def _land_use_from_html(html: str) -> str | None:
    m = re.search(r"Rodzaj działki:?\s*(?:<[^>]+>\s*)*([^<]{1,60})", html)
    return classify_land_use(m.group(1)) if m else None


def parse_detail_page(html: str, title: str | None = None, description: str | None = None) -> dict:
    blobs = ld_json(html)
    listing = _of_type(blobs, "RealEstateListing")
    if listing is None:
        raise LayoutChanged("nieruchomosci-online: brak RealEstateListing w JSON-LD")
    geo = listing.get("geo") or {}
    lat, lon = _num(geo.get("latitude")), _num(geo.get("longitude"))
    url = listing.get("url") or ""
    posted = _date(listing.get("datePosted"))

    land_use, source = _land_use_from_props(listing) or _land_use_from_html(html), "nieruchomosci-online"
    if land_use is None:
        # adres oferty niesie rodzaj, np. /dzialka,budowlana,przy-lesie/123.html
        land_use = classify_land_use(title) or classify_land_use(listing.get("name")) or \
            classify_land_use(url.replace("-", " ").replace(",", " "))
        source = "tytuł"
    if land_use is None:
        texts = [description, listing.get("description")]
        land_use = next((lu for t in texts if (lu := classify_land_use(re.sub(r"<[^>]+>", " ", t or "")))), None)
        source = "opis"
    if land_use is None:
        source = None
    area = next((_num(p.get("value")) for p in listing.get("additionalProperty") or []
                 if isinstance(p, dict) and re.search(r"m²|m2", str(p.get("value") or ""))), None)
    return {
        "lat": lat, "lon": lon,
        # napis "Lokalizacja przybliżona" jest przy każdej mapie, więc o dokładności mówi sam zapis:
        # pinezka działki ma 6+ miejsc po przecinku, środek miejscowości 3–4 (jak na Gratce)
        "precise": lat is not None and lon is not None and min(
            _decimals(geo.get("latitude")), _decimals(geo.get("longitude"))) >= 6,
        "land_use": land_use, "land_use_source": source,
        "area_m2": area,
        "listed_at": posted.isoformat() if posted else None,
        "municipality_hint": ((listing.get("address") or {}).get("addressLocality")),
        "features": _features(listing, html),
    }


def _features(listing: dict, html: str) -> dict:
    pairs = {str(p.get("name")): p.get("value") for p in listing.get("additionalProperty") or []
             if isinstance(p, dict) and p.get("name")}
    f = features.from_params(pairs)
    modified = _date(listing.get("dateModified"))
    if modified:
        f["updated_at"] = modified.isoformat()
    if f["seller"] is None:
        # oznaczenie przy ogłoszeniu, nie w menu strony
        m = re.search(r"(oferta prywatna|bezpośrednio od właściciela|oferta biura|biuro nieruchomości)\s*<", html, re.I)
        f["seller"] = features.seller_from_text(m.group(1)) if m else None
    if f["negotiable"] is None and re.search(r">\s*Cena do negocjacji\s*<", html):
        f["negotiable"] = True
    return f


def scrape(get, cache, observed_at: date, region_slug: str = "dolnoslaskie", teryt_prefix: str = "02",
           max_details: int | None = None, max_pages: int = MAX_PAGES, geo_get=None,
           features_budget: int = 0) -> tuple[list[dict], ScrapeStats]:
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
            log.warning("nieruchomosci-online: strona %d niedostępna, kończę listę", page)
            break
        items, last_seen = parse_search_page(html)
        # stronicowanie pokazuje tylko kilka sąsiednich numerów: granica przesuwa się w trakcie
        total_pages = max(total_pages, last_seen)
        stats.pages += 1
        stats.items_seen += len(items)
        if stats.pages % 20 == 0:
            log.info("nieruchomosci-online: lista, strona %d, ogłoszeń do tej pory %d", stats.pages, len(ads) + len(items))
        new = [it for it in items if it.ad_id not in ads]
        if not new:
            break  # pusta strona albo powtórka poprzedniej: koniec listy
        for it in new:
            ads[it.ad_id] = it
        page += 1
    stats.unique_ads = len(ads)
    log.info("nieruchomosci-online: %d stron, %d unikalnych ogłoszeń", stats.pages, len(ads))
    rows = build_rows(ads.values(), get, cache, observed_at, teryt_prefix, max_details, geo_get, stats,
                      parse_detail_page, "nieruchomosci-online", features_budget=features_budget)
    return rows, stats


def check(region_slug: str = "dolnoslaskie", details: int = 3) -> int:
    """Szybki test na żywej stronie: 1 strona wyników + kilka ofert + ULDK. Wypisuje tylko liczby."""
    from . import uldk
    from .http import PoliteClient

    client = PoliteClient()
    html = client.get(search_url(region_slug, 1))
    items, last = parse_search_page(html)
    links = set(re.findall(r'href="(https://[a-z0-9-]+\.nieruchomosci-online\.pl/dzialka[^"]*/\d+\.html)"', html))
    total = re.findall(r"(\d[\d\s ]{2,})\s*ofert", html)[:2]
    print(f"Wyniki: {len(items)} ofert w JSON-LD, {len(links)} linków do ofert w HTML, "
          f"stronicowanie do: {last}, w tekście: {total}, "
          f"z ceną: {sum(1 for i in items if i.price_pln)}, z metrażem: {sum(1 for i in items if i.area_m2)}")
    ok = bool(items) and sum(1 for i in items if i.price_pln and i.area_m2) >= 0.9 * len(items)
    for it in items[:details]:
        d = parse_detail_page(client.get(it.url), it.title, it.description)
        commune = None
        if d["lat"] is not None:
            commune = uldk.parse_commune_response(PoliteClient(min_delay=0.3, max_delay=0.6).get(
                uldk.commune_url(d["lat"], d["lon"])))
        print(f"  ad {it.ad_id}: cena={it.price_pln} m2={it.area_m2} dodano={d['listed_at']} "
              f"lat={d['lat']} lon={d['lon']} dokładna={d['precise']} typ={d['land_use']} ({d['land_use_source']}) "
              f"gmina={commune} [portal: {d['municipality_hint']}]")
        ok = ok and d["lat"] is not None and commune is not None
    print("WYNIK:", "OK" if ok else "PROBLEM — wklej ten wynik do czatu")
    return 0 if ok else 1
