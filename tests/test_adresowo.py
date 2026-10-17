import json
from datetime import date

import pytest

from lmi.scrapers import adresowo, otodom


def card(aid, price="129 000", area="900", unit="m²", slug=None):
    slug = slug or f"dzialka-budowlana-olawa-chwalibozyce-{aid}"
    return f'''<div data-offer-card="" data-id="{aid}" class="relative flex group">
  <div class="h-48"><span class="pt-0.5 pr-1 text-xs font-bold">6</span></div>
  <div class="isolate flex"><div class="flex pb-1"><div class="flex w-full items-center text-sm">
    <p class="flex-auto text-base text-neutral-900"><span class="font-bold">{price}</span> <span class="text-xs text-neutral-700">zł</span></p>
    <p class="flex-auto text-base text-neutral-900"><span class="font-bold">{area}</span> <span class="text-xs text-neutral-700">{unit}</span></p>
  </div></div>
  <div class="flex pb-3"><h2 class="block flex-1 text-sm"><a href="/o/{slug}" data-track="x">
    <span class="line-clamp-1">Oława, Chwałbożyce</span></a></h2></div>
  <p class="mb-3 line-clamp-4">Sprzedam, tel. 600100200, Jan Kowalski</p></div></div>'''


def search_page(cards, pages=(2, 3)):
    nav = "".join(f'<a href="/dzialki/fds_l{p}">{p}</a>' for p in pages)
    return f"<html><h1>Działki dolnośląskie 3762 ofert</h1>{''.join(cards)}{nav}</html>"


def detail_page(lat=50.862365, lon=17.322521, url="https://adresowo.pl/o/dzialka-budowlana-olawa-c8s0g0",
                name="Działka Oława", description="Działka pod zabudowę jednorodzinną. Kontakt: Jan Kowalski 600100200"):
    offer = {"@context": "http://schema.org", "@graph": [{"@type": "Offer", "price": "129000", "url": url}]}
    place = {"@context": "http://schema.org", "@graph": [{"@type": "Place", "name": name, "description": description,
                                                          "geo": {"@type": "GeoCoordinates", "latitude": lat,
                                                                  "longitude": lon}}]}
    return "".join(f'<script type="application/ld+json">{json.dumps(x)}</script>' for x in (offer, place))


def test_search_url():
    assert adresowo.search_url("dolnoslaskie", 1) == "https://adresowo.pl/dzialki/fds"
    assert adresowo.search_url("dolnoslaskie", 3) == "https://adresowo.pl/dzialki/fds_l3"


def test_parse_search_page():
    items, last = adresowo.parse_search_page(search_page([card("4263582"), card("1", price="1&nbsp;725&nbsp;000", area="3,45",
                                                                                   unit="ha"), card("4263582")],
                                                         pages=(2, 3, 94)))
    assert last == 94 and [i.ad_id for i in items] == ["4263582", "1"]  # powtórzony kafelek raz
    a, b = items
    assert (a.price_pln, a.area_m2) == (129000.0, 900.0)
    assert a.url == "https://adresowo.pl/o/dzialka-budowlana-olawa-chwalibozyce-4263582"
    assert (b.price_pln, b.area_m2) == (1725000.0, 34500.0)  # ha -> m²
    assert "600100200" not in repr(items) and "Kowalski" not in repr(items)


def test_layout_change_detected():
    with pytest.raises(otodom.LayoutChanged):
        adresowo.parse_search_page("<html>nic</html>")
    with pytest.raises(otodom.LayoutChanged):
        adresowo.parse_detail_page("<html>nic</html>")


def test_parse_detail_page():
    d = adresowo.parse_detail_page(detail_page())
    assert (d["lat"], d["lon"], d["precise"], d["price_pln"]) == (50.862365, 17.322521, True, 129000.0)
    assert (d["land_use"], d["land_use_source"]) == ("budowlana", "tytuł")  # z adresu oferty
    assert "Kowalski" not in str(d) and "600100200" not in str(d)
    d = adresowo.parse_detail_page(detail_page(url="https://adresowo.pl/o/dzialka-olawa-x", lat=50.86, lon=17.32))
    assert (d["land_use"], d["land_use_source"], d["precise"]) == ("budowlana", "opis", False)


class Web:
    def __init__(self, pages, details, communes):
        self.pages, self.details, self.communes, self.calls = pages, details, communes, []

    def get(self, url):
        self.calls.append(url)
        if "/dzialki/fds" in url:
            n = int(url.rsplit("_l", 1)[1]) if "_l" in url else 1
            return self.pages[n - 1] if n <= len(self.pages) else "<html><h1>Brak</h1></html>"
        if "/o/" in url:
            return self.details[url.rsplit("-", 1)[1]]
        if "uldk" in url:
            return self.communes.get(url.split("xy=")[1].split(",4326")[0], "-1")
        raise AssertionError(url)


def test_scrape_end_to_end():
    web = Web(
        pages=[search_page([card("1"), card("2")], pages=(2,)), search_page([card("3"), card("4", price="")], pages=(1,))],
        details={"1": detail_page(), "2": detail_page(lat=50.8624, lon=17.3225), "3": detail_page(lat=52.4, lon=16.9), "4": detail_page()},
        communes={"17.322521,50.862365": "0\n021503_2|Oława", "17.322500,50.862400": "0\n021503_2|Oława",
                  "16.900000,52.400000": "0\n306401_1|Poznań"},
    )
    cache = otodom.MemoryCache()
    rows, stats = adresowo.scrape(web.get, cache, date(2026, 10, 17))
    assert stats.pages == 2 and stats.unique_ads == 4  # strona 3 pusta -> koniec
    assert {r["source_listing_id"] for r in rows} == {"1", "2", "4"}  # 4: cena ze strony oferty
    assert stats.skipped_outside_region == 1 and stats.skipped_no_price == 0
    by_id = {r["source_listing_id"]: r for r in rows}
    assert by_id["1"]["lat"] != "" and by_id["2"]["lat"] == ""  # mniej niż 6 miejsc po przecinku
    assert by_id["1"]["municipality_teryt"] == "0215032" and by_id["1"]["land_use"] == "budowlana"
    web.calls.clear()
    adresowo.scrape(web.get, cache, date(2026, 10, 18))
    assert not any("/o/" in c for c in web.calls)  # szczegóły tylko raz


def test_offer_without_pin_and_odd_pages_do_not_stop_the_run():
    no_geo = ('<script type="application/ld+json">{"@graph": [{"@type": "Offer", "price": "1000", '
              '"url": "https://adresowo.pl/o/dzialka-x"}]}</script>')
    d = adresowo.parse_detail_page(no_geo)
    assert d["lat"] is None and d["price_pln"] == 1000.0
    web = Web(pages=[search_page([card("1"), card("2"), card("3")], pages=())],
              details={"1": "<html>strona dewelopera</html>", "2": no_geo, "3": detail_page()},
              communes={"17.322521,50.862365": "0\n021503_2|Oława"})
    cache = otodom.MemoryCache()
    rows, stats = adresowo.scrape(web.get, cache, date(2026, 10, 17))
    assert [r["source_listing_id"] for r in rows] == ["3"]
    assert stats.details_failed == 1 and cache.get_detail("1")["unparsable"]   # zapamiętana, bez ponownego pobierania


def test_many_odd_pages_in_a_row_mean_layout_change():
    from lmi.scrapers import gratka
    n = gratka.LAYOUT_STREAK_LIMIT
    web = Web(pages=[search_page([card(str(i)) for i in range(n)], pages=())],
              details={str(i): "<html>inny wygląd</html>" for i in range(n)}, communes={})
    with pytest.raises(otodom.LayoutChanged):
        adresowo.scrape(web.get, otodom.MemoryCache(), date(2026, 10, 17))
