"""Otodom: działki na sprzedaż w wybranym województwie.

Dane bierzemy z JSON-a __NEXT_DATA__ osadzonego w stronach:
  - wyniki wyszukiwania: props.pageProps.data.searchAds.{items, pagination} (cena, metraż, id)
  - strona oferty:       props.pageProps.ad (współrzędne, typ działki)
Szczegóły oferty pobieramy tylko raz (cache), potem codziennie wystarczą wyniki wyszukiwania.
Gminę (TERYT) ustalamy z współrzędnych przez ULDK (GUGiK), też z cache.

Zapisujemy wyłącznie fakty o działce. Danych sprzedającego (advertOwner, contactDetails,
owner, seller_id) nie odczytujemy.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Protocol

from . import uldk
from .http import FetchError

log = logging.getLogger(__name__)

BASE = "https://www.otodom.pl"
SEARCH_URL = BASE + "/pl/wyniki/sprzedaz/dzialka/{region}?limit=72&by=LATEST&direction=DESC&page={page}"
DETAIL_URL = BASE + "/pl/oferta/{slug}"
MAX_PAGES = 300

LAND_USE = {
    "building": "budowlana",
    "agricultural": "rolna",
    "agricultural_building": "rolno-budowlana",
    "recreational": "rekreacyjna",
    "forest": "leśna",
    "investment": "inwestycyjna",
    "habitat": "siedliskowa",
}


class LayoutChanged(Exception):
    """Strona nie ma oczekiwanej struktury — Otodom zmienił frontend, parser do poprawki."""


def next_data(html: str) -> dict:
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise LayoutChanged("brak __NEXT_DATA__")
    return json.loads(m.group(1))


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value")
    try:
        f = float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


# --------------------------------------------------------------------------- wyniki


@dataclass(frozen=True)
class SearchItem:
    ad_id: str
    slug: str
    price_pln: float | None
    area_m2: float | None


def parse_search_page(html: str) -> tuple[list[SearchItem], int]:
    """Zwraca (ogłoszenia, liczba stron)."""
    try:
        search_ads = next_data(html)["props"]["pageProps"]["data"]["searchAds"]
        raw_items = search_ads["items"]
    except (KeyError, TypeError) as exc:
        raise LayoutChanged(f"brak searchAds.items ({exc})") from exc
    total_pages = int((search_ads.get("pagination") or {}).get("totalPages") or 1)

    items = []
    for it in raw_items or []:
        if not isinstance(it, dict) or it.get("id") is None or not it.get("slug"):
            continue
        if it.get("estate") not in (None, "TERRAIN") or it.get("transaction") not in (None, "SELL"):
            continue
        price = None if it.get("hidePrice") else _num(it.get("totalPrice"))
        area = _num(it.get("areaInSquareMeters")) or _num(it.get("terrainAreaInSquareMeters"))
        items.append(SearchItem(str(it["id"]), it["slug"], price, area))
    return items, total_pages


# --------------------------------------------------------------------------- szczegóły


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def parse_detail_page(html: str) -> dict:
    """Wyciąga ze strony oferty to, czego nie ma w wynikach. Zwraca dict do cache."""
    try:
        ad = next_data(html)["props"]["pageProps"]["ad"]
    except (KeyError, TypeError) as exc:
        raise LayoutChanged(f"brak pageProps.ad ({exc})") from exc
    if not isinstance(ad, dict):
        raise LayoutChanged("pageProps.ad nie jest obiektem")

    location = ad.get("location") or {}
    coords = location.get("coordinates") or {}
    target = ad.get("target") or {}

    land_type = _first(target.get("Type"))
    municipality_hint = None
    for loc in (location.get("reverseGeocoding") or {}).get("locations") or []:
        level = str(loc.get("locationLevel") or "").lower()
        if "munic" in level or "gmina" in level:
            municipality_hint = loc.get("name") or loc.get("fullName")
            break
    if municipality_hint is None:
        municipality_hint = target.get("City") or target.get("Subregion")

    lat, lon = _num(coords.get("latitude")), _num(coords.get("longitude"))
    radius = (location.get("mapDetails") or {}).get("radius")
    return {
        "lat": lat,
        "lon": lon,
        "precise": radius == 0,
        "land_use": LAND_USE.get(str(land_type), land_type),
        "area_m2": _num(target.get("Area")),
        "municipality_hint": municipality_hint,
    }


# --------------------------------------------------------------------------- przebieg


class Cache(Protocol):
    def get_detail(self, ad_id: str) -> dict | None: ...
    def put_detail(self, ad_id: str, slug: str, detail: dict) -> None: ...
    def get_commune(self, key: str) -> tuple[str, str | None] | None: ...
    def put_commune(self, key: str, teryt: str, name: str | None) -> None: ...


class MemoryCache:
    def __init__(self):
        self.details: dict[str, dict] = {}
        self.communes: dict[str, tuple[str, str | None]] = {}

    def get_detail(self, ad_id):
        return self.details.get(ad_id)

    def put_detail(self, ad_id, slug, detail):
        self.details[ad_id] = detail

    def get_commune(self, key):
        return self.communes.get(key)

    def put_commune(self, key, teryt, name):
        self.communes[key] = (teryt, name)


@dataclass
class ScrapeStats:
    pages: int = 0
    items_seen: int = 0
    unique_ads: int = 0
    rows: int = 0
    details_fetched: int = 0
    details_failed: int = 0
    details_deferred: int = 0
    uldk_calls: int = 0
    skipped_no_price: int = 0
    skipped_no_area: int = 0
    skipped_no_location: int = 0
    skipped_outside_region: int = 0
    notes: list[str] = field(default_factory=list)


def scrape(
    get: Callable[[str], str],
    cache: Cache,
    observed_at: date,
    region_slug: str = "dolnoslaskie",
    teryt_prefix: str = "02",
    max_details: int | None = None,
    max_pages: int = MAX_PAGES,
    geo_get: Callable[[str], str] | None = None,
) -> tuple[list[dict], ScrapeStats]:
    """Jeden przebieg: wszystkie strony wyników + brakujące szczegóły + gminy.

    `get(url) -> html` — zwykle PoliteClient.get; w testach podmieniany.
    `max_details` ogranicza liczbę nowych stron ofert w jednym przebiegu (reszta w kolejnym).
    `geo_get` — osobny klient dla ULDK (krótsze przerwy niż dla Otodom); domyślnie `get`.
    """
    geo_get = geo_get or get
    stats = ScrapeStats()
    ads: dict[str, SearchItem] = {}
    page, total_pages = 1, 1
    while page <= min(total_pages, max_pages):
        items, total_pages = parse_search_page(get(SEARCH_URL.format(region=region_slug, page=page)))
        stats.pages += 1
        stats.items_seen += len(items)
        if not items:
            break
        for it in items:
            ads.setdefault(it.ad_id, it)  # sortowanie po dacie: nowe ogłoszenia mogą przesunąć strony
        page += 1
    stats.unique_ads = len(ads)
    log.info("otodom: %d stron, %d unikalnych ogłoszeń", stats.pages, len(ads))

    names: dict[str, str] = {}
    rows = []
    for it in ads.values():
        if it.price_pln is None:
            stats.skipped_no_price += 1
            continue

        detail = cache.get_detail(it.ad_id)
        if detail is None:
            if max_details is not None and stats.details_fetched >= max_details:
                stats.details_deferred += 1
                continue
            try:
                detail = parse_detail_page(get(DETAIL_URL.format(slug=it.slug)))
            except FetchError as exc:  # np. ogłoszenie zdjęte w trakcie przebiegu
                stats.details_failed += 1
                log.warning("otodom: szczegóły %s: %s", it.ad_id, exc)
                continue
            stats.details_fetched += 1
            cache.put_detail(it.ad_id, it.slug, detail)

        area = it.area_m2 or detail.get("area_m2")
        if area is None:
            stats.skipped_no_area += 1
            continue
        if detail.get("lat") is None or detail.get("lon") is None:
            stats.skipped_no_location += 1
            continue

        key = f"{detail['lat']:.4f},{detail['lon']:.4f}"  # ~10 m; sąsiednie działki dzielą wynik
        commune = cache.get_commune(key)
        if commune is None:
            stats.uldk_calls += 1
            try:
                commune = uldk.parse_commune_response(geo_get(uldk.commune_url(detail["lat"], detail["lon"])))
            except FetchError as exc:
                log.warning("uldk: %s", exc)
                commune = None
            if commune is None:
                stats.skipped_no_location += 1
                continue
            cache.put_commune(key, *commune)
        teryt, uldk_name = commune
        if not teryt.startswith(teryt_prefix):
            stats.skipped_outside_region += 1
            continue
        # jedna nazwa na gminę w całym pliku (pierwsza znana)
        # Bez nazwy z ULDK bierzemy wskazówkę z Otodomu (bywa nazwą miejscowości, nie gminy)
        # i dopisujemy TERYT, żeby nie pomylić gminy z wsią.
        fallback = f"{detail.get('municipality_hint') or 'gmina'} [{teryt}]"
        name = names.setdefault(teryt, uldk_name or fallback)

        rows.append({
            "source_listing_id": it.ad_id,
            "observed_at": observed_at.isoformat(),
            "municipality_teryt": teryt,
            "municipality_name": name,
            "parcel_id": "",
            # niedokładne pinezki (radius > 0) pomijamy, żeby nie łączyć działek po przybliżeniu
            "lat": f"{detail['lat']:.6f}" if detail.get("precise") else "",
            "lon": f"{detail['lon']:.6f}" if detail.get("precise") else "",
            "area_m2": f"{area:.2f}",
            "price_pln": f"{it.price_pln:.2f}",
            "land_use": detail.get("land_use") or "",
            "url": DETAIL_URL.format(slug=it.slug),
            "title": "",
        })
    stats.rows = len(rows)
    return rows, stats
