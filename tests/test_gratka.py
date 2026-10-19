from datetime import date

import pytest

from lmi.scrapers import gratka, otodom
from lmi.scrapers.http import FetchError
from lmi.scrapers.nuxt import unflatten

from fixtures_gratka import detail_page, flatten, node, search_page


def test_flatten_roundtrip():
    obj = {"a": [1, {"b": None, "c": "x"}], "d": True}
    assert unflatten(flatten(obj)) == obj


def test_parse_search_page():
    items, pages = gratka.parse_search_page(search_page([node(1), node(2, price=None), node(3, area="1 391,5")],
                                                        total=3337))
    assert pages == 1113  # 3337 / 3 na stronę w teście
    a = items[0]
    assert (a.ad_id, a.price_pln, a.area_m2, a.listed_at) == ("1", 1628627.0, 16300.0, date(2026, 9, 1))
    assert a.url == "https://gratka.pl/nieruchomosci/dzialka-legnicki-milkowice/ob/1"
    assert items[1].price_pln is not None  # bez ceny całkowitej: cena za m² x metraż
    assert items[2].area_m2 == 1391.5
    assert "Kowalski" not in repr(items) and "600100200" not in repr(items)


def test_layout_change_detected():
    with pytest.raises(otodom.LayoutChanged):
        gratka.parse_search_page("<html>nic</html>")


def test_parse_detail_page():
    d = gratka.parse_detail_page(detail_page(params=[{"label": "Typ działki", "value": "rolno-budowlana"}]))
    assert (d["lat"], d["lon"], d["precise"]) == (51.2851, 16.155, False)
    assert (d["land_use"], d["land_use_source"]) == ("rolno-budowlana", "gratka")
    assert d["municipality_hint"] == "Miłkowice" and "Kowalski" not in str(d)
    d = gratka.parse_detail_page(detail_page(), title="Działka budowlana z WZ")
    assert (d["land_use"], d["land_use_source"]) == ("budowlana", "tytuł")


class Web:
    def __init__(self, pages, details, communes):
        self.pages, self.details, self.communes, self.calls = pages, details, communes, []

    def get(self, url):
        self.calls.append(url)
        if "dzialki-grunty" in url:
            assert "page=1" not in url  # Gratka zwraca 404 dla ?page=1
            n = int(url.rsplit("page=", 1)[1]) if "page=" in url else 1
            if n > len(self.pages):
                raise FetchError("404")
            return self.pages[n - 1]
        if "/ob/" in url:
            return self.details[url.rsplit("/", 1)[1]]
        if "uldk" in url:
            return self.communes.get(url.split("xy=")[1].split(",4326")[0], "-1")
        raise AssertionError(url)


def test_scrape_end_to_end():
    web = Web(
        pages=[search_page([node(1), node(2)], total=4), search_page([node(3), node(4, price=None, area=None)], total=4)],
        details={"1": detail_page(), "2": detail_page(title="Działka leśna"), "3": detail_page(lat=52.4, lon=16.9),
                 "4": detail_page()},
        communes={"16.155000,51.285100": "0\n020905_2|Miłkowice", "16.900000,52.400000": "0\n306401_1|Poznań"},
    )
    cache = otodom.MemoryCache()
    rows, stats = gratka.scrape(web.get, cache, date(2026, 10, 17))
    assert stats.pages == 2 and stats.unique_ads == 4
    assert {r["source_listing_id"] for r in rows} == {"1", "2"}
    assert stats.skipped_outside_region == 1 and stats.skipped_no_price == 1
    r = rows[0]
    assert r["municipality_teryt"] == "0209052" and r["municipality_name"] == "Miłkowice (gm. wiejska)"
    assert r["lat"] == "" and r["listed_at"] == "2026-09-01" and r["url"].endswith("/ob/1")
    assert {x["land_use"] for x in rows} == {"", "leśna"}
    assert sum("uldk" in c for c in web.calls) == 2  # ten sam punkt raz
    # drugi dzień: tylko strony wyników
    web.calls.clear()
    gratka.scrape(web.get, cache, date(2026, 10, 18))
    assert all("dzialki-grunty" in c for c in web.calls)


def test_search_url():
    assert gratka.search_url("dolnoslaskie", 1) == "https://gratka.pl/nieruchomosci/dzialki-grunty/dolnoslaskie"
    assert gratka.search_url("dolnoslaskie", 3).endswith("dolnoslaskie?page=3")


def test_missing_later_page_ends_listing():
    web = Web(pages=[search_page([node(1)], total=5)], details={"1": detail_page()},
              communes={"16.155000,51.285100": "0\n020905_2|Miłkowice"})
    rows, stats = gratka.scrape(web.get, otodom.MemoryCache(), date(2026, 10, 17))
    assert stats.pages == 1 and len(rows) == 1


def test_precise_pin_vs_town_center():
    assert gratka.parse_detail_page(detail_page(lat=51.11382622, lon=16.91037529))["precise"] is True
    assert gratka.parse_detail_page(detail_page(lat=51.2851, lon=16.155))["precise"] is False


def test_parse_views():
    html = "<div>Numer ogłoszenia gratka-1211-34</div><div>Liczba odsłon</div> <span>1 207</span><script>x</script>"
    assert gratka.parse_views(html) == 1207
    assert gratka.parse_views("<div>Brak licznika</div>") is None


def test_views_are_measured_and_refreshed():
    page = detail_page() + "<p>Liczba odsłon 7</p>"
    web = Web(pages=[search_page([node(1)], total=1)], details={"1": page},
              communes={"16.155000,51.285100": "0\n020905_2|Miłkowice"})
    cache = otodom.MemoryCache()
    gratka.scrape(web.get, cache, date(2026, 10, 17), interest_budget=50)
    assert cache.get_detail("1")["views_log"] == [{"date": "2026-10-17", "views": 7, "saved": None}]
    web.details["1"] = detail_page() + "<p>Liczba odsłon 19</p>"
    web.calls.clear()
    gratka.scrape(web.get, cache, date(2026, 10, 18), interest_budget=50)   # za wcześnie (oferta stara: co 7 dni)
    assert not any("/ob/" in c for c in web.calls)
    gratka.scrape(web.get, cache, date(2026, 10, 24), interest_budget=50)
    assert cache.get_detail("1")["stats"]["views"] == 19


def test_detail_features_from_params():
    d = gratka.parse_detail_page(detail_page(params=[
        {"label": "Media", "value": ["prąd", "woda", "kanalizacja"]}, {"label": "Dojazd", "value": "asfaltowy"},
        {"label": "Ogrodzenie", "value": "brak"}, {"label": "Aktualizacja", "value": "21.05.2026"},
        {"label": "Telefon", "value": "600100200"}]))
    f = d["features"]
    assert f["media"] == ["kanalizacja", "prąd", "woda"] and f["access"] == ["asfaltowy"] and f["fence"] is False
    assert f["updated_at"] == "2026-05-21" and "600100200" not in str(f)


def test_old_details_get_features_within_budget():
    web = Web(pages=[search_page([node(1), node(2)], total=2)], details={"1": detail_page(), "2": detail_page()},
              communes={"16.155000,51.285100": "0\n020905_2|Miłkowice"})
    cache = otodom.MemoryCache()
    for i in ("1", "2"):  # pobrane przed zbieraniem parametrów
        cache.put_detail(i, "u", {"lat": 51.2851, "lon": 16.155, "precise": False, "land_use": "rolna"})
    gratka.build_rows(gratka.parse_search_page(web.pages[0])[0], web.get, cache, date(2026, 10, 17), "02", None,
                      web.get, otodom.ScrapeStats(), gratka.parse_detail_page, "gratka", features_budget=1)
    assert sum("features" in cache.get_detail(i) for i in ("1", "2")) == 1


def test_owner_type_sets_seller():
    f = gratka.parse_features({"offer": {"ownerType": "user"}}, {}, "")
    assert f["seller"] == "prywatny" and f["params"]["ownerType"] == "user"
    assert gratka.parse_features({"offer": {"ownerType": "FIRM"}}, {}, "")["seller"] == "biuro"
    assert gratka.parse_features({"offer": {"ownerType": "xyz1"}}, {}, "")["seller"] is None   # nowy kod: surowy w params


def test_owner_type_from_flat_nuxt_data():
    html = '<script id="__NUXT_DATA__" type="application/json">[{"a": 1}, {"ownerType": 2}, "user"]</script>'
    assert gratka.parse_features({}, {}, html)["seller"] == "prywatny"
