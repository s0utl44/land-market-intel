"""Sztuczne strony Gratki: __NUXT_DATA__ w formacie devalue, struktura jak w zwiadzie z serwera (2026-10)."""
import json


def flatten(obj) -> list:
    """Odwrotność nuxt.unflatten: obiekt -> płaska tablica devalue (z opakowaniem ShallowReactive na korzeniu)."""
    out: list = []

    def add(v):
        idx = len(out)
        out.append(None)
        if isinstance(v, dict):
            out[idx] = {k: add(x) for k, x in v.items()}
        elif isinstance(v, list):
            out[idx] = [add(x) for x in v]
        else:
            out[idx] = v
        return idx

    out.append(["ShallowReactive", 1])
    add(obj)
    return out


def page(state: dict) -> str:
    return ('<html><script type="application/json" data-nuxt-data="nuxt-app" id="__NUXT_DATA__">'
            + json.dumps(flatten(state)) + "</script></html>")


def node(ad_id, price=1628627, area="16300", added="2026-09-01T10:00:00+02:00", title="Działka", url=None):
    return {
        "addedAt": added, "refreshedAt": None, "advertisementText": "x", "area": area,
        "contact": {"person": {"name": "Jan Kowalski", "phones": ["600100200"]}, "company": {"name": "Biuro"}},
        "description": "Działka w okolicy", "id": 1500000000 + ad_id, "idOnFrontend": str(ad_id),
        "location": {"location": ["dolnośląskie", "legnicki", "Miłkowice", "Miłkowice"], "street": None},
        "price": None if price is None else {"amount": f"{price:.2f}", "currency": "PLN"},
        "priceM2": {"amount": "99.92", "currency": "PLN"},
        "title": title, "url": url or f"/nieruchomosci/dzialka-legnicki-milkowice/ob/{ad_id}",
    }


def search_page(nodes, total=None):
    return page({"data": {"property-listing-data-/nieruchomosci/dzialki-grunty/dolnoslaskie": {
        "data": {"searchResult": {"properties": {"nodes": nodes, "totalCount": total or len(nodes)}}}}}})


def detail_page(lat=51.2851, lon=16.155, params=None, title="Działka", area="16300"):
    return page({"data": {"property-details-x": {"data": {"propertyData": {
        "area": area, "title": title, "description": "Opis",
        "location": {"map": {"center": {"latitude": lat, "longitude": lon}}, "county": "legnicki", "commune": "Miłkowice"},
        "parameters": params or [],
        "contact": {"person": {"name": "Jan Kowalski"}},
    }}}}})
