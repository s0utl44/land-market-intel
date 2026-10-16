"""Sztuczne strony Otodom o strukturze zgodnej z prawdziwą (zwiad z VPS, 2026-10)."""
import json


def _wrap(next_data: dict) -> str:
    return ('<html><head></head><body><script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">'
            + json.dumps(next_data) + "</script></body></html>")


def search_item(ad_id, price=329000, area=1636, hide_price=False, estate="TERRAIN",
                created_first="2025-03-14T09:12:00+00:00", pushed_up=None):
    return {
        "id": ad_id, "title": "Działka", "slug": f"dzialka-{ad_id}-ID{ad_id}", "estate": estate,
        "transaction": "SELL", "agency": None, "areaInSquareMeters": area,
        "terrainAreaInSquareMeters": None, "hidePrice": hide_price,
        "totalPrice": None if price is None else {"value": price, "currency": "PLN"},
        "pricePerSquareMeter": {"value": 201.1, "currency": "PLN"},
        "location": {"mapDetails": {"radius": 0}, "address": {"street": {"name": "x", "number": None},
                                                              "city": None, "province": None}},
        "advertOwner": {"name": "Jan", "contacts": [{"name": "Jan"}]},
        "dateCreated": "2026-10-01T10:00:00Z",
        "createdAtFirst": created_first,
        "pushedUpAt": pushed_up,
    }


def search_page(items, total_pages=1):
    return _wrap({"props": {"pageProps": {"data": {"searchAds": {
        "items": items,
        "pagination": {"itemsPerPage": 72, "totalItems": len(items) * total_pages, "totalPages": total_pages},
    }}}}})


def detail_page(lat=50.960144, lon=17.407703, radius=0, land_type="building", area="1636",
                levels=(("voivodeship", "dolnośląskie"), ("county", "oławski"), ("municipality", "Oława"),
                        ("village", "Bystrzyca"))):
    return _wrap({"props": {"pageProps": {"ad": {
        "id": 1,
        "target": {"Area": area, "City": "Bystrzyca", "Price": 329000, "Price_per_m": 201,
                   "Province": "dolnoslaskie", "Subregion": "olawski", "Type": [land_type],
                   "seller_id": "1234567", "hidePrice": "0"},
        "location": {
            "coordinates": None if lat is None else {"latitude": lat, "longitude": lon, "__typename": "Coordinates"},
            "mapDetails": {"radius": radius, "zoom": 17},
            "reverseGeocoding": {"locations": [
                {"id": f"x{i}", "locationLevel": lvl, "name": name, "fullName": name}
                for i, (lvl, name) in enumerate(levels)]},
            "address": {"street": {"name": "x", "number": None}, "city": None},
        },
        "owner": {"name": "Jan", "phones": ["600100200"]},
    }}}})
