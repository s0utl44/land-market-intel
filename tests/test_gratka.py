from datetime import date

import pytest

from lmi.scrapers import gratka, otodom
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
            return self.pages[int(url.rsplit("page=", 1)[1]) - 1]
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
