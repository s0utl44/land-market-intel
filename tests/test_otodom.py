from datetime import date

import pytest

from lmi import csv_import
from lmi.scrapers import otodom, uldk
from lmi.scrapers.http import Blocked, FetchError

from fixtures_otodom import detail_page, search_item, search_page


def test_parse_search_page():
    items, pages = otodom.parse_search_page(search_page(
        [search_item(1), search_item(2, price=None), search_item(3, hide_price=True), search_item(4, estate="FLAT")],
        total_pages=58))
    assert pages == 58
    assert [i.ad_id for i in items] == ["1", "2", "3"]  # mieszkanie odrzucone
    assert items[0] == otodom.SearchItem("1", "dzialka-1-ID1", 329000.0, 1636.0, date(2025, 3, 14), None, "Działka")
    assert items[1].price_pln is None and items[2].price_pln is None


def test_parse_detail_page():
    d = otodom.parse_detail_page(detail_page())
    assert d == {"lat": 50.960144, "lon": 17.407703, "precise": True, "land_use": "budowlana",
                 "land_use_source": "otodom", "area_m2": 1636.0, "municipality_hint": "Oława"}


def test_detail_does_not_keep_seller_data():
    d = otodom.parse_detail_page(detail_page())
    assert "600100200" not in str(d) and "Jan" not in str(d) and "1234567" not in str(d)


def test_detail_approximate_location_and_unknown_type():
    d = otodom.parse_detail_page(detail_page(radius=3, land_type="something_new"))
    assert d["precise"] is False and d["land_use"] == "something_new"


def test_layout_change_is_detected():
    with pytest.raises(otodom.LayoutChanged):
        otodom.parse_search_page("<html>bez danych</html>")
    with pytest.raises(otodom.LayoutChanged):
        otodom.parse_search_page(search_page([]).replace("searchAds", "searchResults"))


@pytest.mark.parametrize("body, expected", [
    ("0\n026401_1|Wrocław", ("0264011", "Wrocław (gm. miejska)")),
    ("0\n021505_2|", ("0215052", None)),        # tak odpowiedziało ULDK w zwiadzie: pusta nazwa
    ("0\n021505_2", ("0215052", None)),
    ("-1 brak wyników", None),
    ("", None),
])
def test_uldk_parser(body, expected):
    assert uldk.parse_commune_response(body) == expected


class FakeWeb:
    def __init__(self, pages, details, communes, missing=()):
        self.pages, self.details, self.communes, self.missing = pages, details, communes, set(missing)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if "/pl/wyniki/" in url:
            page = int(url.rsplit("page=", 1)[1])
            return self.pages[page - 1]
        if "/pl/oferta/" in url:
            slug = url.rsplit("/", 1)[1]
            if slug in self.missing:
                raise FetchError("404")
            return self.details[slug]
        if "uldk" in url:
            return self.communes.get(url.split("xy=")[1].split(",4326")[0], "-1 brak")
        raise AssertionError(url)


def make_web():
    p1 = search_page([search_item(1), search_item(2, price=None), search_item(3)], total_pages=2)
    p2 = search_page([search_item(3), search_item(4, area=None), search_item(5)], total_pages=2)
    details = {
        "dzialka-1-ID1": detail_page(lat=51.1, lon=17.0),
        "dzialka-3-ID3": detail_page(lat=51.2, lon=17.1, radius=5, land_type="agricultural"),
        "dzialka-4-ID4": detail_page(lat=51.1, lon=17.0, area="900"),          # metraż tylko w szczegółach
        "dzialka-5-ID5": detail_page(lat=52.4, lon=16.9),                       # poza dolnośląskim
    }
    communes = {
        "17.000000,51.100000": "0\n026401_1|Wrocław",
        "17.100000,51.200000": "0\n022305_2|",
        "16.900000,52.400000": "0\n306401_1|Poznań",
    }
    return FakeWeb([p1, p2], details, communes)


def test_scrape_end_to_end(tmp_path):
    web = make_web()
    cache = otodom.MemoryCache()
    rows, stats = otodom.scrape(web.get, cache, date(2026, 10, 16))
    assert stats.pages == 2 and stats.unique_ads == 5  # ogłoszenie 3 na obu stronach liczone raz
    assert stats.skipped_no_price == 1 and stats.skipped_outside_region == 1
    by_id = {r["source_listing_id"]: r for r in rows}
    assert set(by_id) == {"1", "3", "4"}
    assert by_id["1"]["municipality_teryt"] == "0264011"
    assert by_id["1"]["municipality_name"] == "Wrocław (gm. miejska)"
    assert by_id["1"]["lat"] == "51.100000"
    assert by_id["3"]["lat"] == "" and by_id["3"]["land_use"] == "rolna"  # niedokładna pinezka
    assert by_id["3"]["municipality_name"] == "Oława [0223052]"           # ULDK bez nazwy
    assert by_id["4"]["area_m2"] == "900.00"
    # ULDK raz na punkt: ogłoszenia 1 i 4 mają te same współrzędne
    assert sum("uldk" in c for c in web.calls) == 3

    # wiersze przechodzą walidację importu
    import csv
    from lmi.synthetic import CSV_COLUMNS
    path = tmp_path / "o.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    parsed = csv_import.parse_file(path)
    assert parsed.ok, parsed.errors


def test_second_run_uses_cache():
    web = make_web()
    cache = otodom.MemoryCache()
    otodom.scrape(web.get, cache, date(2026, 10, 16))
    web.calls.clear()
    rows, stats = otodom.scrape(web.get, cache, date(2026, 10, 17))
    assert stats.details_fetched == 0 and stats.uldk_calls == 0
    assert all("/pl/wyniki/" in c for c in web.calls)  # tylko strony wyników
    assert len(rows) == 3


def test_max_details_defers_the_rest():
    web = make_web()
    rows, stats = otodom.scrape(web.get, otodom.MemoryCache(), date(2026, 10, 16), max_details=1)
    assert stats.details_fetched == 1 and stats.details_deferred == 3 and len(rows) == 1


def test_removed_ad_is_skipped_not_fatal():
    web = make_web()
    web.missing.add("dzialka-1-ID1")
    rows, stats = otodom.scrape(web.get, otodom.MemoryCache(), date(2026, 10, 16))
    assert stats.details_failed == 1 and "1" not in {r["source_listing_id"] for r in rows}


def test_blocked_propagates():
    def get(url):
        raise Blocked("403")
    with pytest.raises(Blocked):
        otodom.scrape(get, otodom.MemoryCache(), date(2026, 10, 16))


def test_listing_dates_from_search():
    items, _ = otodom.parse_search_page(search_page([
        search_item(1, pushed_up="2026-10-10T07:00:00Z"),
        search_item(2, created_first=None),            # brak createdAtFirst -> dateCreated
        search_item(3, created_first="bzdura"),
    ]))
    assert items[0].listed_at == date(2025, 3, 14) and items[0].pushed_up_at == date(2026, 10, 10)
    assert items[1].listed_at == date(2026, 10, 1)
    assert items[2].listed_at == date(2026, 10, 1)


def test_rows_carry_listing_dates():
    rows, _ = otodom.scrape(make_web().get, otodom.MemoryCache(), date(2026, 10, 16))
    assert {r["listed_at"] for r in rows} == {"2025-03-14"}
    assert {r["pushed_up_at"] for r in rows} == {""}


@pytest.mark.parametrize("text, expected", [
    ("Działka budowlana 1391 m² Wrocław", "budowlana"),          # tytuły z Twojego testu
    ("Sprzedam działkę BUDOWLANĄ, media w drodze", "budowlana"),
    ("Działka rolno-budowlana z WZ", "rolno-budowlana"),
    ("Działka rolno budowlana", "rolno-budowlana"),
    ("Działka siedliskowa z sadem", "siedliskowa"),
    ("Działka pod zabudowę jednorodzinną", "budowlana"),
    ("Działka rekreacyjna nad jeziorem", "rekreacyjna"),
    ("Las 2 ha, działka leśna", "leśna"),
    ("Działka inwestycyjna przy S8, usługowa", "inwestycyjna"),
    ("Działka rolna 3 ha, klasa IV", "rolna"),
    ("Działka 1200 m², Oława", None),
    ("", None),
])
def test_classify_land_use(text, expected):
    assert otodom.classify_land_use(text) == expected


def test_detail_without_type_uses_title_then_description():
    d = otodom.parse_detail_page(detail_page(land_type=None, title="Działka budowlana 900 m²"))
    assert (d["land_use"], d["land_use_source"]) == ("budowlana", "tytuł")
    d = otodom.parse_detail_page(detail_page(land_type=None, title="Działka 900 m²",
                                             description="<p>Działka <b>rolna</b>, klasa IVa.</p>"))
    assert (d["land_use"], d["land_use_source"]) == ("rolna", "opis")
    d = otodom.parse_detail_page(detail_page(land_type=None, title="Działka", description=""))
    assert (d["land_use"], d["land_use_source"]) == (None, None)


def test_cached_offers_without_type_get_it_from_title_or_one_refetch():
    web = make_web()
    cache = otodom.MemoryCache()
    otodom.scrape(web.get, cache, date(2026, 10, 16))
    # symulujemy oferty pobrane wcześniej bez rodzaju
    for d in cache.details.values():
        d["land_use"] = None
    web.pages = [search_page([search_item(1, title="Działka budowlana Oława"), search_item(3)], total_pages=1)]
    web.details["dzialka-3-ID3"] = detail_page(lat=51.2, lon=17.1, land_type=None, title="Działka",
                                               description="Piękna działka leśna")
    web.calls.clear()
    rows, stats = otodom.scrape(web.get, cache, date(2026, 10, 17))
    by_id = {r["source_listing_id"]: r for r in rows}
    assert by_id["1"]["land_use"] == "budowlana"     # z tytułu, bez zapytania
    assert by_id["3"]["land_use"] == "leśna"         # z opisu, po jednym ponownym pobraniu strony
    assert stats.land_use_filled == 2 and stats.land_use_refetched == 1
    assert sum("/pl/oferta/" in c for c in web.calls) == 1
    # kolejny dzień: nic nie pobieramy ponownie
    web.calls.clear()
    otodom.scrape(web.get, cache, date(2026, 10, 18))
    assert not any("/pl/oferta/" in c for c in web.calls)
