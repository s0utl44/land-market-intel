import json
from datetime import date

import pytest

from lmi.scrapers import nonline, otodom

BASE = "https://dolnoslaskie.nieruchomosci-online.pl/dzialki,sprzedaz/"


def offer(i, price="499000", area="891.00", slug="dzialka,na-sprzedaz"):
    return {"@type": "Offer", "price": price, "priceCurrency": "PLN",
            "url": f"https://wroclaw.nieruchomosci-online.pl/{slug}/{2670000 + i}.html",
            "name": f"Działka {i}",
            "itemOffered": {"@type": "Accommodation", "description": "Ładna działka, dzwoń: Jan Kowalski 600100200",
                            "address": {"addressLocality": "Wrocław"},
                            "floorSize": {"@type": "QuantitativeValue", "value": area, "unitCode": "MTR"}}}


def search_page(offers, pages=(2, 3)):
    ld = {"@context": "https://schema.org", "@type": "CollectionPage",
          "mainEntity": {"@type": "Product", "offers": [{"@type": "AggregateOffer", "offerCount": str(len(offers)),
                                                         "offers": offers}]}}
    nav = "".join(f'<a href="{BASE}?p={p}">{p}</a>' for p in pages)
    return (f'<html><script type="application/ld+json">{json.dumps(ld)}</script>'
            f'<script type="application/ld+json">{{"@type": "WebSite"}}</script>{nav}</html>')


def detail_page(lat="51.142864425654125", lon="16.826552449876402", props=None, approximate=False,
                url="https://wroclaw.nieruchomosci-online.pl/dzialka,na-sprzedaz/2670001.html", name="Działka",
                rodzaj_html=None):
    ld = {"@type": "RealEstateListing", "name": name, "url": url, "description": "opis",
          "additionalProperty": props if props is not None else [{"@type": "PropertyValue", "name": "Pow. dz.",
                                                                  "value": "891.00m²"}],
          "address": {"addressLocality": "Wrocław"},
          "geo": {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon},
          "agent": {"@type": "RealEstateAgent", "name": "Jan Kowalski", "telephone": "600100200"},
          "datePosted": "2026-10-10 12:00:00.000"}
    html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    if approximate:
        html += "<div>Lokalizacja przybliżona</div>"
    if rodzaj_html:
        html += f"<li><span>Rodzaj działki:</span> <strong>{rodzaj_html}</strong></li>"
    return html


def test_search_url():
    assert nonline.search_url("dolnoslaskie", 1) == BASE
    assert nonline.search_url("dolnoslaskie", 3) == BASE + "?p=3"


def test_parse_search_page():
    items, last = nonline.parse_search_page(search_page([offer(1), offer(2, area="1 200,5")], pages=(2, 3, 82)))
    assert last == 82
    a = items[0]
    assert (a.ad_id, a.price_pln, a.area_m2) == ("2670001", 499000.0, 891.0)
    assert items[1].area_m2 == 1200.5
    assert "600100200" not in repr(items[0].url)


def test_layout_change_detected():
    with pytest.raises(otodom.LayoutChanged):
        nonline.parse_search_page("<html>nic</html>")
    with pytest.raises(otodom.LayoutChanged):
        nonline.parse_detail_page("<html>nic</html>")


def test_parse_detail_page():
    d = nonline.parse_detail_page(detail_page(props=[{"name": "Rodzaj działki", "value": "budowlana"},
                                                     {"name": "Pow. dz.", "value": "1664.00m²"}]))
    assert (d["lat"], d["lon"], d["precise"]) == (51.142864425654125, 16.826552449876402, True)
    assert (d["land_use"], d["land_use_source"], d["area_m2"]) == ("budowlana", "nieruchomosci-online", 1664.0)
    assert d["listed_at"] == "2026-10-10" and "Kowalski" not in str(d) and "600100200" not in str(d)
    # rodzaj w HTML-u parametrów
    d = nonline.parse_detail_page(detail_page(rodzaj_html="rolna"))
    assert (d["land_use"], d["land_use_source"]) == ("rolna", "nieruchomosci-online")
    # rodzaj z adresu oferty ("przy-lesie" to nie działka leśna)
    d = nonline.parse_detail_page(detail_page(url="https://x.nieruchomosci-online.pl/dzialka,budowlana,przy-lesie/1.html"))
    assert (d["land_use"], d["land_use_source"]) == ("budowlana", "tytuł")
    d = nonline.parse_detail_page(detail_page(url="https://x.nieruchomosci-online.pl/dzialka,przy-lesie/1.html"))
    assert d["land_use"] is None


def test_approximate_location_is_not_precise():
    assert nonline.parse_detail_page(detail_page(approximate=True))["precise"] is False


class Web:
    def __init__(self, pages, details, communes):
        self.pages, self.details, self.communes, self.calls = pages, details, communes, []

    def get(self, url):
        self.calls.append(url)
        if "dzialki,sprzedaz" in url:
            n = int(url.rsplit("?p=", 1)[1]) if "?p=" in url else 1
            return self.pages[n - 1] if n <= len(self.pages) else self.pages[-1]  # portal powtarza ostatnią
        if url.endswith(".html"):
            return self.details[url.rsplit("/", 1)[1][:-5]]
        if "uldk" in url:
            return self.communes.get(url.split("xy=")[1].split(",4326")[0], "-1")
        raise AssertionError(url)


def test_scrape_end_to_end():
    # stronicowanie na stronie 1 pokazuje tylko do 2, dalej odsłania się 3; strona 4 powtarza 3 -> koniec
    web = Web(
        pages=[search_page([offer(1), offer(2)], pages=(2,)), search_page([offer(3)], pages=(1, 3)),
               search_page([offer(4, price=None)], pages=(2, 3, 4))],
        details={"2670001": detail_page(), "2670002": detail_page(approximate=True),
                 "2670003": detail_page(lat="52.4", lon="16.9")},
        communes={"16.826552,51.142864": "0\n026401_1|Wrocław", "16.900000,52.400000": "0\n306401_1|Poznań"},
    )
    cache = otodom.MemoryCache()
    rows, stats = nonline.scrape(web.get, cache, date(2026, 10, 17))
    assert stats.pages == 4 and stats.unique_ads == 4
    assert {r["source_listing_id"] for r in rows} == {"2670001", "2670002"}
    assert stats.skipped_outside_region == 1 and stats.skipped_no_price == 1
    by_id = {r["source_listing_id"]: r for r in rows}
    assert by_id["2670001"]["lat"] != "" and by_id["2670002"]["lat"] == ""  # przybliżona pinezka
    assert by_id["2670001"]["municipality_teryt"] == "0264011" and by_id["2670001"]["listed_at"] == "2026-10-10"
    assert all("?pn" not in c and "?o=" not in c for c in web.calls)
    web.calls.clear()
    nonline.scrape(web.get, cache, date(2026, 10, 18))
    assert not any(c.endswith(".html") for c in web.calls)  # szczegóły tylko raz
