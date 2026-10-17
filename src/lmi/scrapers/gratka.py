"""Gratka: działki na sprzedaż w województwie.

Dane z __NUXT_DATA__ (stan aplikacji Nuxt osadzony w stronie):
  - wyniki: ...searchResult.properties.{nodes, totalCount} (35 ofert na stronę, ?page=N)
  - strona oferty: propertyData (współrzędne środka mapy, powiat, gmina, parametry)
robots.txt Gratki zabrania filtrów w adresie i /api-gratka, więc chodzimy tylko po zwykłej liście.
Danych kontaktowych (contact.person / contact.company) nie odczytujemy.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime

from . import interest, uldk
from .http import FetchError
from .nuxt import find_first, nuxt_data
from .otodom import LayoutChanged, ScrapeStats, classify_land_use

log = logging.getLogger(__name__)

BASE = "https://gratka.pl"
LIST_URL = BASE + "/nieruchomosci/dzialki-grunty/{region}"


def search_url(region: str, page: int) -> str:
    """Strona 1 istnieje tylko bez parametru: "?page=1" zwraca 404."""
    return LIST_URL.format(region=region) + ("" if page <= 1 else f"?page={page}")
MAX_PAGES = 300


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("amount", v.get("value"))
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = re.sub(r"[^\d,.]", "", str(v)).replace(",", ".")
    if s.count(".") > 1:  # "1.234.567" -> separatory tysięcy
        s = s.replace(".", "")
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f > 0 else None


def _date(v) -> date | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
        return date.fromisoformat(m.group(1)) if m else None


@dataclass(frozen=True)
class GratkaItem:
    ad_id: str
    url: str
    price_pln: float | None
    area_m2: float | None
    listed_at: date | None
    refreshed_at: date | None
    title: str | None
    description: str | None


def _listing(nd) -> dict:
    found = find_first(nd, lambda d: isinstance(d.get("properties"), dict) and "nodes" in d["properties"])
    if found is None:
        raise LayoutChanged("gratka: brak searchResult.properties.nodes")
    return found["properties"]


def _item(node: dict) -> GratkaItem | None:
    ad_id = node.get("idOnFrontend") or node.get("id")
    url = node.get("url") or ""
    if not ad_id or not url:
        return None
    url = url if url.startswith("http") else BASE + url
    area = _num(node.get("area"))
    price = None
    for key in ("price", "totalPrice", "priceTotal"):
        if node.get(key) is not None:
            price = _num(node[key])
            break
    if price is None and area:  # awaryjnie: cena za m² x metraż
        per_m2 = next((_num(node[k]) for k in ("priceM2", "pricePerM2", "pricePerSquareMeter") if node.get(k)), None)
        price = round(per_m2 * area, -2) if per_m2 else None
    return GratkaItem(
        ad_id=str(ad_id), url=url, price_pln=price, area_m2=area,
        listed_at=_date(node.get("addedAt")), refreshed_at=_date(node.get("refreshedAt")),
        title=node.get("title"), description=node.get("description"),
    )


def parse_search_page(html: str) -> tuple[list[GratkaItem], int]:
    """Zwraca (ogłoszenia, liczba stron)."""
    nd = nuxt_data(html)
    if nd is None:
        raise LayoutChanged("gratka: brak __NUXT_DATA__")
    props = _listing(nd)
    nodes = props.get("nodes") or []
    items = [i for i in (_item(n) for n in nodes if isinstance(n, dict)) if i is not None]
    total = int(props.get("totalCount") or len(items) or 0)
    per_page = max(len(nodes), 1)
    return items, max(1, math.ceil(total / per_page))


def _land_use_from_params(pd: dict) -> str | None:
    """Rodzaj działki z parametrów oferty (np. "Typ działki: budowlana")."""
    for lst_key, lst in pd.items():
        if not isinstance(lst, list):
            continue
        for p in lst:
            if not isinstance(p, dict):
                continue
            label = " ".join(str(p.get(k) or "") for k in ("label", "name", "title", "key")).lower()
            if re.search(r"typ|rodzaj|przeznacz", label) and "dzia" in label or "przeznacz" in label:
                value = p.get("value") or p.get("values")
                text = " ".join(map(str, value)) if isinstance(value, list) else str(value or "")
                if (lu := classify_land_use(text)):
                    return lu
    return None


VIEWS = re.compile(r"Liczba\s+ods[lł]on\D{0,20}?(\d[\d\s\u00a0]*)", re.I)
GRATKA_NEW_EVERY, GRATKA_OLD_EVERY = 2, 7  # dni


def parse_views(html: str) -> int | None:
    """Licznik "Liczba odsłon N" ze strony oferty (tekst, nie dane Nuxt)."""
    text = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", html, flags=re.S)).split())
    m = VIEWS.search(text)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def parse_detail_page(html: str, title: str | None = None, description: str | None = None) -> dict:
    nd = nuxt_data(html)
    pd = find_first(nd, lambda d: isinstance(d.get("propertyData"), dict)) if nd is not None else None
    if pd is None:
        raise LayoutChanged("gratka: brak propertyData")
    pd = pd["propertyData"]
    loc = pd.get("location") or {}
    center = ((loc.get("map") or {}).get("center")) or {}
    lat, lon = _num(center.get("latitude")), _num(center.get("longitude"))
    # pinezka działki ma zwykle 6+ miejsc po przecinku; środek miejscowości 3–4
    precise = lat is not None and lon is not None and all(
        len(repr(float(v)).split(".")[-1]) >= 6 for v in (lat, lon))

    land_use, source = _land_use_from_params(pd), "gratka"
    if land_use is None:
        land_use = classify_land_use(title) or classify_land_use(pd.get("title"))
        source = "tytuł"
    if land_use is None:
        texts = [description, pd.get("description")]
        land_use = next((lu for t in texts if (lu := classify_land_use(re.sub(r"<[^>]+>", " ", t or "")))), None)
        source = "opis"
    if land_use is None:
        source = None
    return {
        "lat": lat, "lon": lon,
        "precise": precise,
        "land_use": land_use, "land_use_source": source,
        "area_m2": _num(pd.get("area")),
        "municipality_hint": loc.get("commune"),
        "county_hint": loc.get("county"),
        "views": parse_views(html),
    }


def scrape(get, cache, observed_at: date, region_slug: str = "dolnoslaskie", teryt_prefix: str = "02",
           max_details: int | None = None, max_pages: int = MAX_PAGES, geo_get=None,
           interest_budget: int = 0) -> tuple[list[dict], ScrapeStats]:
    """Wszystkie strony wyników + brakujące strony ofert (raz na ofertę) + gminy z ULDK
    + ponowny pomiar liczby odsłon dla ofert, którym minął termin (najwyżej `interest_budget`)."""
    geo_get = geo_get or get
    stats = ScrapeStats()
    ads: dict[str, GratkaItem] = {}
    page, total_pages = 1, 1
    while page <= min(total_pages, max_pages):
        try:
            html = get(search_url(region_slug, page))
        except FetchError:
            if page == 1:
                raise
            log.warning("gratka: strona %d niedostępna, kończę listę", page)  # np. liczba ofert spadła w trakcie
            break
        items, total_pages = parse_search_page(html)
        stats.pages += 1
        stats.items_seen += len(items)
        if not items:
            break
        for it in items:
            ads.setdefault(it.ad_id, it)
        page += 1
    stats.unique_ads = len(ads)
    log.info("gratka: %d stron, %d unikalnych ogłoszeń", stats.pages, len(ads))
    rows = build_rows(ads.values(), get, cache, observed_at, teryt_prefix, max_details, geo_get, stats,
                      parse_detail_page, "gratka")
    interest.refresh(ads.values(), cache, observed_at, interest_budget,
                     lambda it, detail: (parse_views(get(it.url)), None), stats, "gratka",
                     GRATKA_NEW_EVERY, GRATKA_OLD_EVERY)
    return rows, stats


LAYOUT_STREAK_LIMIT = 20  # tyle nietypowych stron ofert z rzędu = zmiana wyglądu portalu


def build_rows(items, get, cache, observed_at: date, teryt_prefix: str, max_details: int | None, geo_get,
               stats: ScrapeStats, parse_detail, label: str, price_from_detail: bool = False) -> list[dict]:
    """Wspólne dla portali z listą + stroną oferty: brakujące szczegóły (raz na ofertę), gmina z ULDK, wiersze CSV.

    `parse_detail(html, title, description)` zwraca słownik z lat/lon/precise/land_use/area_m2
    (opcjonalnie listed_at, gdy data dodania jest tylko na stronie oferty, i price_pln,
    gdy `price_from_detail` i na liście ceny zabrakło).
    """
    names: dict[str, str] = {}
    rows = []
    layout_streak = 0
    for it in items:
        if it.price_pln is None and not price_from_detail:
            stats.skipped_no_price += 1
            continue
        detail = cache.get_detail(it.ad_id)
        if detail is None:
            if max_details is not None and stats.details_fetched >= max_details:
                stats.details_deferred += 1
                continue
            try:
                detail = parse_detail(get(it.url), it.title, it.description)
                layout_streak = 0
            except FetchError as exc:
                stats.details_failed += 1
                log.warning("%s: szczegóły %s: %s", label, it.ad_id, exc)
                continue
            except LayoutChanged as exc:
                # pojedyncza nietypowa strona (np. oferta dewelopera, zdjęta w trakcie) nie zatrzymuje przebiegu;
                # dopiero seria takich stron oznacza, że portal zmienił wygląd
                layout_streak += 1
                stats.details_failed += 1
                log.warning("%s: nietypowa strona oferty %s: %s", label, it.ad_id, exc)
                if layout_streak >= LAYOUT_STREAK_LIMIT:
                    raise LayoutChanged(f"{label}: {layout_streak} stron ofert z rzędu bez oczekiwanych danych "
                                        f"(ostatnia: {exc})") from exc
                cache.put_detail(it.ad_id, it.url, {"lat": None, "lon": None, "unparsable": str(exc)[:200]})
                continue
            stats.details_fetched += 1
            if "views" in detail:  # pierwszy pomiar licznika (portale, które go pokazują)
                interest.record(detail, observed_at, detail.pop("views"))
            cache.put_detail(it.ad_id, it.url, detail)
            if stats.details_fetched % 100 == 0:
                log.info("%s: pobrano szczegóły %d nowych ofert", label, stats.details_fetched)

        price = it.price_pln or detail.get("price_pln")
        if price is None:
            stats.skipped_no_price += 1
            continue
        area = it.area_m2 or detail.get("area_m2")
        if area is None:
            stats.skipped_no_area += 1
            continue
        if detail.get("lat") is None or detail.get("lon") is None:
            stats.skipped_no_location += 1
            continue
        key = f"{detail['lat']:.4f},{detail['lon']:.4f}"
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
        name = names.setdefault(teryt, uldk_name or f"{detail.get('municipality_hint') or 'gmina'} [{teryt}]")
        listed = it.listed_at or _date(detail.get("listed_at"))
        rows.append({
            "source_listing_id": it.ad_id,
            "observed_at": observed_at.isoformat(),
            "municipality_teryt": teryt,
            "municipality_name": name,
            "parcel_id": "",
            # położenie przybliżone (np. środek miejscowości) pomijamy, żeby nie łączyć duplikatów po takim położeniu
            "lat": f"{detail['lat']:.6f}" if detail.get("precise") else "",
            "lon": f"{detail['lon']:.6f}" if detail.get("precise") else "",
            "area_m2": f"{area:.2f}",
            "price_pln": f"{price:.2f}",
            "land_use": detail.get("land_use") or "",
            "url": it.url,
            "title": "",
            "listed_at": listed.isoformat() if listed and listed <= observed_at else "",
            "pushed_up_at": it.refreshed_at.isoformat()
            if it.refreshed_at and it.refreshed_at <= observed_at else "",
        })
    stats.rows = len(rows)
    return rows


def check(region_slug: str = "dolnoslaskie", details: int = 3) -> int:
    """Szybki test na żywej stronie: 1 strona wyników + kilka ofert + ULDK. Wypisuje tylko liczby."""
    from .http import PoliteClient

    client = PoliteClient()
    html = client.get(search_url(region_slug, 1))
    items, pages = parse_search_page(html)
    node = (_listing(nuxt_data(html)).get("nodes") or [{}])[0]
    print("Pola oferty na liście:", sorted(k for k in node if k != "contact"))
    print("Pola ceny:", {k: v for k, v in node.items() if "price" in k.lower()})
    print(f"Wyniki: {len(items)} ofert na stronie 1, stron: {pages}, "
          f"z ceną: {sum(1 for i in items if i.price_pln)}, z metrażem: {sum(1 for i in items if i.area_m2)}, "
          f"z datą dodania: {sum(1 for i in items if i.listed_at)}")
    complete = sum(1 for i in items if i.price_pln and i.area_m2)
    ok = bool(items) and complete >= 0.9 * len(items)  # pojedyncze oferty bez metrażu się zdarzają
    for it in items[:details]:
        d = parse_detail_page(client.get(it.url), it.title, it.description)
        commune = None
        if d["lat"] is not None:
            commune = uldk.parse_commune_response(PoliteClient(min_delay=0.3, max_delay=0.6).get(
                uldk.commune_url(d["lat"], d["lon"])))
        print(f"  ad {it.ad_id}: cena={it.price_pln} m2={it.area_m2} zł/m2={round(it.price_pln / it.area_m2) if it.price_pln and it.area_m2 else None} "
              f"dodano={it.listed_at} lat={d['lat']} lon={d['lon']} typ={d['land_use']} ({d['land_use_source']}) "
              f"gmina={commune} [gratka: {d['municipality_hint']}, pow. {d['county_hint']}]")
        ok = ok and d["lat"] is not None and commune is not None
    print("WYNIK:", "OK" if ok else "PROBLEM — wklej ten wynik do czatu")
    return 0 if ok else 1
