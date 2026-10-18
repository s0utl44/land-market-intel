"""Deduplikacja: łączenie ogłoszeń (z różnych portali lub powtórzonych) w jedną nieruchomość.

Reguły (od najmocniejszej):
  1. parcel_id   — ten sam znormalizowany identyfikator działki.
  2. location    — odległość <= max_distance_m i różnica powierzchni <= location_area_tol.
  3. price_area  — "wspólne mianowniki", gdy któreś ogłoszenie nie ma dokładnej pinezki (albo obie
                   pinezki są do 1 km od siebie — wtedy o punkt więcej): ta sama gmina, oba wystawione w tym samym czasie (okresy
                   widoczności nachodzą na siebie albo przerwa <= price_area_max_gap_days, np. ponowne
                   wystawienie), powierzchnia <= price_area_area_tol. Punkty: zgodna powierzchnia 2,
                   nieokrągła powierzchnia (np. 1636 m²) +1, cena <= 0,5% +2 albo <= 3% +1, ten sam typ
                   działki +1; łączymy od PRICE_AREA_MIN_SCORE i tylko jednoznacznie (jeden kandydat
                   z danego portalu, albo kilka identycznych kopii — to samo ogłoszenie wystawione wielokrotnie).
                   Cena różna o 3–15% tylko przy identycznym, nieokrągłym metrażu i tym samym typie (właściciel
                   vs biuro); inny typ działki nie wyklucza (portale różnie go nazywają).
Dwa ogłoszenia z RÓŻNYMI parcel_id nigdy nie trafiają do jednej nieruchomości (także pośrednio).
Ogłoszenia z jednego portalu widoczne w tym samym czasie łączymy tylko, gdy są niemal identyczne
(metraż <= 1%, cena <= 2%) — inaczej to zwykle sąsiednie działki z jednego podziału.
Łączenie jest przechodnie (union-find), od najmocniejszych par, z tymi zakazami na poziomie grup.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from typing import Iterable

ALGORITHM_VERSION = "dedup-v4"
PRICE_AREA_MIN_SCORE = 4

METHOD_CONFIDENCE = {
    "single": 1.00,
    "parcel_id": 0.99,
    "location": 0.85,
    "price_area": 0.60,
}
_METHOD_RANK = {"parcel_id": 3, "location": 2, "price_area": 1}


@dataclass(frozen=True)
class DedupParams:
    max_distance_m: float = 150.0
    location_area_tol: float = 0.05
    price_area_area_tol: float = 0.005
    price_area_price_tol: float = 0.15   # powyżej 3% tylko przy identycznym, nieokrągłym metrażu i tym samym typie
    price_area_max_gap_days: int = 14
    price_area_max_distance_m: float = 1000.0
    same_source_area_tol: float = 0.01
    same_source_price_tol: float = 0.02

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Listing:
    source_id: str
    source_listing_id: str
    municipality_teryt: str
    area_m2: float
    first_seen: date
    last_seen: date
    prices: set[float] = field(default_factory=set)
    parcel_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    land_use: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_id, self.source_listing_id)

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass(frozen=True)
class Link:
    source_id: str
    source_listing_id: str
    property_key: str
    match_method: str
    match_confidence: float


def normalize_parcel_id(value: str | None) -> str | None:
    if not value:
        return None
    norm = "".join(value.split()).upper()
    return norm or None


def listings_from_observations(rows: Iterable[dict]) -> list[Listing]:
    """Agreguje obserwacje (dicty z kluczami jak w core.listing_observations) do ogłoszeń.

    Dla atrybutów zmiennych w czasie bierze wartość z najnowszej obserwacji, która ją ma.
    """
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["source_id"], r["source_listing_id"])].append(r)

    listings = []
    for (source_id, listing_id), obs in grouped.items():
        obs.sort(key=lambda r: r["observed_at"])
        latest = obs[-1]

        def last_non_null(name: str):
            for r in reversed(obs):
                if r.get(name) is not None:
                    return r[name]
            return None

        lat, lon = None, None
        for r in reversed(obs):
            if r.get("lat") is not None and r.get("lon") is not None:
                lat, lon = float(r["lat"]), float(r["lon"])
                break
        listings.append(
            Listing(
                source_id=source_id,
                source_listing_id=listing_id,
                municipality_teryt=latest["municipality_teryt"],
                area_m2=float(latest["area_m2"]),
                first_seen=obs[0]["observed_at"],
                last_seen=latest["observed_at"],
                prices={float(r["price_pln"]) for r in obs},
                parcel_id=normalize_parcel_id(last_non_null("parcel_id")),
                lat=lat,
                lon=lon,
                land_use=last_non_null("land_use") or None,
            )
        )
    return listings


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _rel_diff(a: float, b: float) -> float:
    return abs(a - b) / max(a, b)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _parcel_conflict(a: Listing, b: Listing) -> bool:
    return a.parcel_id is not None and b.parcel_id is not None and a.parcel_id != b.parcel_id


def _prices_close(a: Listing, b: Listing, tol: float) -> bool:
    return any(_rel_diff(pa, pb) <= tol for pa in a.prices for pb in b.prices)


def _price_gap(a: Listing, b: Listing) -> float:
    return min(_rel_diff(pa, pb) for pa in a.prices for pb in b.prices)


def _overlap(a: Listing, b: Listing, gap_days: int = 0) -> bool:
    """Okresy widoczności nachodzą na siebie (albo przerwa między nimi <= gap_days)."""
    return a.first_seen <= b.last_seen + timedelta(days=gap_days) and \
        b.first_seen <= a.last_seen + timedelta(days=gap_days)


def _same_source_clash(a: Listing, b: Listing, params: DedupParams) -> bool:
    """Dwa ogłoszenia z jednego portalu, widoczne naraz i nie bliźniacze: osobne działki (np. z jednego podziału)."""
    return (a.source_id == b.source_id and _overlap(a, b)
            and not (_rel_diff(a.area_m2, b.area_m2) <= params.same_source_area_tol
                     and _price_gap(a, b) <= params.same_source_price_tol))


def attribute_score(a: Listing, b: Listing, params: DedupParams) -> int:
    """Punkty zgodności dla pary bez wspólnej dokładnej pinezki; 0 = wykluczone."""
    if _rel_diff(a.area_m2, b.area_m2) > params.price_area_area_tol:
        return 0
    gap = _price_gap(a, b)
    if gap > params.price_area_price_tol:
        return 0
    nonround = bool(round(a.area_m2) % 100 and round(b.area_m2) % 100)
    if gap > 0.03 and not (nonround and _rel_diff(a.area_m2, b.area_m2) <= 0.002):
        # ta sama działka bywa u właściciela taniej niż u biura (np. 842 m²: 88 i 99 tys.), ale taką różnicę
        # przyjmujemy tylko przy identycznym, nieokrągłym metrażu
        return 0
    # inny typ działki nie wyklucza: portale różnie nazywają to samo (budowlana / rolno-budowlana / inwestycyjna)
    score = 2
    if nonround:
        score += 1                       # nieokrągły metraż rzadko się powtarza przypadkiem
    score += 2 if gap <= 0.005 else 1 if gap <= 0.03 else 0
    if a.land_use and a.land_use == b.land_use:
        score += 1
    return score


def candidate_pairs(listings: list[Listing], params: DedupParams) -> list[tuple[int, int, str]]:
    """Zwraca pary (i, j, metoda) spełniające którąkolwiek regułę."""
    pairs: list[tuple[int, int, str]] = []

    # 1. parcel_id
    by_parcel: dict[str, list[int]] = defaultdict(list)
    for i, l in enumerate(listings):
        if l.parcel_id:
            by_parcel[l.parcel_id].append(i)
    for idx in by_parcel.values():
        for i, j in combinations(idx, 2):
            pairs.append((i, j, "parcel_id"))

    # 2. location — siatka o boku ~max_distance_m, porównujemy sąsiednie komórki
    cell_deg_lat = params.max_distance_m / 111_320.0
    grid: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for i, l in enumerate(listings):
        if l.has_coords:
            cell_deg_lon = cell_deg_lat / max(math.cos(math.radians(l.lat)), 0.1)
            grid[(l.municipality_teryt, int(l.lat // cell_deg_lat), int(l.lon // cell_deg_lon))].append(i)
    for (muni, cy, cx), idx in grid.items():
        neighbours: list[int] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbours.extend(grid.get((muni, cy + dy, cx + dx), ()))
        for i in idx:
            a = listings[i]
            for j in neighbours:
                if j <= i:
                    continue
                b = listings[j]
                if _parcel_conflict(a, b) or _same_source_clash(a, b, params):
                    continue
                if (
                    _rel_diff(a.area_m2, b.area_m2) <= params.location_area_tol
                    and haversine_m(a.lat, a.lon, b.lat, b.lon) <= params.max_distance_m
                ):
                    pairs.append((i, j, "location"))

    # 3. price_area — wspólne mianowniki, gdy brak dokładnej pinezki po którejś stronie (albo pinezki blisko)
    by_muni: dict[str, list[int]] = defaultdict(list)
    for i, l in enumerate(listings):
        by_muni[l.municipality_teryt].append(i)
    ok: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for idx in by_muni.values():
        by_area = sorted(idx, key=lambda k: listings[k].area_m2)
        for pos, i in enumerate(by_area):
            a = listings[i]
            # kandydaci tylko z wąskiego przedziału metrażu (lista posortowana), każda para raz
            for j in by_area[pos + 1:]:
                b = listings[j]
                if b.area_m2 > a.area_m2 * (1 + params.price_area_area_tol) + 0.01:
                    break
                if a.has_coords and b.has_coords and \
                        haversine_m(a.lat, a.lon, b.lat, b.lon) > params.price_area_max_distance_m:
                    continue
                if (_parcel_conflict(a, b) or _same_source_clash(a, b, params)
                        or not _overlap(a, b, params.price_area_max_gap_days)):
                    continue
                # obie dokładne pinezki dalej niż reguła lokalizacji: potrzeba mocniejszej zgodności
                need = PRICE_AREA_MIN_SCORE + (1 if a.has_coords and b.has_coords else 0)
                if attribute_score(a, b, params) >= need:
                    ok[i][b.source_id].append(j)
                    ok[j][a.source_id].append(i)
    # tylko pary jednoznaczne z obu stron: jeden kandydat z danego portalu albo dwa bliźniacze
    # (to samo ogłoszenie wystawione w portalu dwa razy: ten sam metraż i cena, pinezki do 30 m albo brak)
    def twins(x: int, y: int) -> bool:
        a, b = listings[x], listings[y]
        if a.has_coords and b.has_coords and haversine_m(a.lat, a.lon, b.lat, b.lon) > 30:
            return False                 # dwie dokładne pinezki w różnych miejscach: dwie działki
        return _rel_diff(a.area_m2, b.area_m2) <= 0.005 and _price_gap(a, b) <= 0.005

    def unambiguous(cands: list[int]) -> bool:
        # jeden kandydat albo kilka identycznych kopii (to samo ogłoszenie wystawione wielokrotnie)
        return len(cands) == 1 or all(twins(x, y) for x, y in combinations(cands, 2))

    price_area = {(min(i, j), max(i, j)) for i, per_src in ok.items() for src, cands in per_src.items()
                  if unambiguous(cands) for j in cands
                  if j != i and listings[j].source_id != listings[i].source_id
                  and i in ok[j][listings[i].source_id] and unambiguous(ok[j][listings[i].source_id])}
    # bliźniacze ogłoszenia z jednego portalu (podwójne wystawienie) też łączymy
    price_area |= {(min(i, j), max(i, j)) for i, per_src in ok.items()
                   for j in per_src.get(listings[i].source_id, [])
                   if j != i and twins(i, j) and unambiguous(per_src[listings[i].source_id])}
    pairs.extend((i, j, "price_area") for i, j in sorted(price_area))
    return pairs


def deduplicate(listings: list[Listing], params: DedupParams | None = None) -> list[Link]:
    params = params or DedupParams()
    uf = _UnionFind(len(listings))
    best_method: dict[int, str] = {}
    members: dict[int, list[int]] = {i: [i] for i in range(len(listings))}

    def group_conflict(ra: int, rb: int) -> bool:
        return any(_parcel_conflict(listings[x], listings[y]) or _same_source_clash(listings[x], listings[y], params)
                   for x in members[ra] for y in members[rb])

    # od najmocniejszych par: słabsze nie mogą skleić grup, które się wykluczają
    def strength(p):
        # najpierw mocniejsza metoda, w jej obrębie pary najbardziej zgodne (cena, metraż, odległość):
        # słabsze dopasowanie nie może zająć miejsca dokładnego bliźniaka
        a, b = listings[p[0]], listings[p[1]]
        dist = haversine_m(a.lat, a.lon, b.lat, b.lon) if a.has_coords and b.has_coords else 0.0
        return (-_METHOD_RANK[p[2]], round(_price_gap(a, b), 3), round(_rel_diff(a.area_m2, b.area_m2), 3), dist,
                a.key, b.key)

    for i, j, method in sorted(candidate_pairs(listings, params), key=strength):
        ra, rb = uf.find(i), uf.find(j)
        if ra == rb:
            continue
        if group_conflict(ra, rb):
            continue
        uf.union(i, j)
        root = uf.find(i)
        merged = members.pop(ra) + members.pop(rb)
        members[root] = merged
        for k in (i, j):
            if _METHOD_RANK[method] > _METHOD_RANK.get(best_method.get(k, ""), 0):
                best_method[k] = method

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(listings)):
        clusters[uf.find(i)].append(i)

    links: list[Link] = []
    for members in clusters.values():
        anchor = min(listings[i].key for i in members)
        property_key = "P-" + hashlib.sha1("|".join(anchor).encode()).hexdigest()[:12]
        for i in members:
            method = best_method.get(i, "single") if len(members) > 1 else "single"
            links.append(
                Link(
                    source_id=listings[i].source_id,
                    source_listing_id=listings[i].source_listing_id,
                    property_key=property_key,
                    match_method=method,
                    match_confidence=METHOD_CONFIDENCE[method],
                )
            )
    return links


def review(listings: list[Listing], links: list[Link], params: DedupParams | None = None,
           examples: int = 25) -> dict:
    """Kontrola jakości po deduplikacji (dla panelu administratora):
      - suspicious: grupy, w których ceny lub metraże za bardzo się różnią (może złe połączenie),
      - near_miss: pary z różnych grup, które prawie spełniają regułę (może przeoczony duplikat),
      - outliers: ogłoszenia z nieprawdopodobną ceną za m² albo metrażem (błąd w ogłoszeniu lub parserze).
    """
    params = params or DedupParams()
    by_key = {l.key: l for l in listings}
    prop_of = {(k.source_id, k.source_listing_id): k.property_key for k in links}
    groups_: dict[str, list[Listing]] = defaultdict(list)
    for k in links:
        groups_[k.property_key].append(by_key[(k.source_id, k.source_listing_id)])
    multi = {p: g for p, g in groups_.items() if len(g) > 1}
    suspicious = []
    for p, g in multi.items():
        prices = [min(l.prices) for l in g]
        areas = [l.area_m2 for l in g]
        if max(prices) / min(prices) > 1.25 or max(areas) / min(areas) > 1 + params.location_area_tol:
            suspicious.append({"property": p, "listings": [f"{l.source_id}:{l.source_listing_id}" for l in g],
                               "prices": sorted(prices), "areas": sorted(areas)})
    near = []
    by_muni: dict[str, list[Listing]] = defaultdict(list)
    for l in listings:
        by_muni[l.municipality_teryt].append(l)
    for ls in by_muni.values():
        ls.sort(key=lambda l: l.area_m2)
        for pos, a in enumerate(ls):
            for b in ls[pos + 1:]:
                if b.area_m2 > a.area_m2 * (1 + params.price_area_area_tol) + 0.01:
                    break
                if prop_of[a.key] == prop_of[b.key] or a.source_id == b.source_id or not _overlap(a, b, 14):
                    continue
                if attribute_score(a, b, params) == PRICE_AREA_MIN_SCORE - 1:
                    near.append({"a": f"{a.source_id}:{a.source_listing_id}", "b": f"{b.source_id}:{b.source_listing_id}",
                                 "area": a.area_m2, "prices": [min(a.prices), min(b.prices)]})
    # możliwe duplikaty, których reguły nie łączą: ten sam metraż, cena do 15%, widoczne naraz,
    # pinezki blisko albo brak; osobno z jednego portalu (np. kilka biur) i z różnych
    possible: dict[str, list] = {"same_source": [], "cross_source": []}
    for ls in by_muni.values():
        for pos, a in enumerate(ls):
            for b in ls[pos + 1:]:
                if b.area_m2 > a.area_m2 * (1 + params.price_area_area_tol) + 0.01:
                    break
                if prop_of[a.key] == prop_of[b.key] or not _overlap(a, b, 14) or _price_gap(a, b) > 0.15:
                    continue
                dist = haversine_m(a.lat, a.lon, b.lat, b.lon) if a.has_coords and b.has_coords else None
                if dist is not None and dist > 100:
                    continue
                possible["same_source" if a.source_id == b.source_id else "cross_source"].append({
                    "a": f"{a.source_id}:{a.source_listing_id}", "b": f"{b.source_id}:{b.source_listing_id}",
                    "area": a.area_m2, "prices": [min(a.prices), min(b.prices)],
                    "dist_m": round(dist) if dist is not None else None, "land_use": [a.land_use, b.land_use]})
    outliers = []
    for l in listings:
        ppm2 = min(l.prices) / l.area_m2
        if ppm2 < 2 or ppm2 > 4000 or l.area_m2 < 100 or l.area_m2 > 2_000_000:
            outliers.append({"listing": f"{l.source_id}:{l.source_listing_id}", "area": l.area_m2,
                             "price": min(l.prices), "ppm2": round(ppm2, 1)})
    methods: dict[str, int] = defaultdict(int)
    for k in links:
        methods[k.match_method] += 1
    return {
        "listings": len(listings), "properties": len(groups_), "multi_listing_properties": len(multi),
        "methods": dict(methods),
        "suspicious": len(suspicious), "suspicious_examples": suspicious[:examples],
        "near_miss": len(near), "near_miss_examples": near[:examples],
        "outliers": len(outliers), "outlier_examples": outliers[:examples],
        "possible_same_source": len(possible["same_source"]), "possible_same_source_examples": possible["same_source"][:examples],
        "possible_cross_source": len(possible["cross_source"]),
        "possible_cross_source_examples": possible["cross_source"][:examples],
        "by_source": {src: {"listings": sum(1 for k in by_key if k[0] == src),
                            "properties": len({prop_of[k] for k in by_key if k[0] == src}),
                            "only_this_portal": sum(1 for g in groups_.values() if {l.source_id for l in g} == {src})}
                      for src in sorted({k[0] for k in by_key})},
    }


def explain_pair(a: Listing, b: Listing, params: DedupParams | None = None) -> str:
    """Dlaczego obecne reguły nie łączą wprost tej pary (do porównań wersji deduplikacji)."""
    params = params or DedupParams()
    if a.municipality_teryt != b.municipality_teryt:
        return "inna gmina"
    if _parcel_conflict(a, b):
        return "różne numery działek"
    if _same_source_clash(a, b, params):
        return "ten sam portal, widoczne naraz, różna cena/metraż"
    dist = haversine_m(a.lat, a.lon, b.lat, b.lon) if a.has_coords and b.has_coords else None
    if dist is not None and dist <= params.max_distance_m and _rel_diff(a.area_m2, b.area_m2) <= params.location_area_tol:
        return "spełnia regułę pinezki (rozdzielone przez konflikt w grupie)"
    if not _overlap(a, b, params.price_area_max_gap_days):
        return "nie były widoczne w tym samym czasie"
    if _rel_diff(a.area_m2, b.area_m2) > params.price_area_area_tol:
        return f"metraż różny o {_rel_diff(a.area_m2, b.area_m2) * 100:.1f}%" + (f", pinezki {dist:.0f} m" if dist else "")
    if _price_gap(a, b) > params.price_area_price_tol:
        return f"cena różna o {_price_gap(a, b) * 100:.1f}%"
    score = attribute_score(a, b, params)
    need = PRICE_AREA_MIN_SCORE + (1 if a.has_coords and b.has_coords else 0)
    if score < need:
        return f"za mało punktów ({score} z {need}: okrągły metraż / cena nie identyczna)"
    return "niejednoznaczne (kilku kandydatów z jednego portalu) albo konflikt w grupie"


def diff_runs(listings: list[Listing], old: dict, new: dict, params: DedupParams | None = None,
              examples: int = 3) -> dict:
    """Pary połączone w `old` (klucz ogłoszenia -> działka), a rozdzielone w `new`, z powodami."""
    params = params or DedupParams()
    by_key = {l.key: l for l in listings}
    old_groups: dict[str, list] = defaultdict(list)
    for k, p in old.items():
        if k in by_key and k in new:
            old_groups[p].append(k)
    new_members: dict[str, list] = defaultdict(list)
    for k, p in new.items():
        if k in by_key:
            new_members[p].append(k)
    reasons: dict[str, list] = defaultdict(list)
    for keys in old_groups.values():
        if len({new[k] for k in keys}) < 2:
            continue
        for x, y in combinations(keys, 2):
            if new[x] == new[y]:
                continue
            a, b = by_key[x], by_key[y]
            dist = haversine_m(a.lat, a.lon, b.lat, b.lon) if a.has_coords and b.has_coords else None
            why = explain_pair(a, b, params)
            if why.startswith(("niejednoznaczne", "spełnia regułę")):
                # która para z obu grup się wyklucza (ten sam portal naraz albo różne numery działek)
                clash = next(((x2, y2) for x2 in new_members[new[x]] for y2 in new_members[new[y]]
                              if _parcel_conflict(by_key[x2], by_key[y2])
                              or _same_source_clash(by_key[x2], by_key[y2], params)), None)
                if clash:
                    c1, c2 = by_key[clash[0]], by_key[clash[1]]
                    why = (f"konflikt w grupie: {c1.source_id}:{c1.source_listing_id} ({c1.area_m2:.0f} m², "
                           f"{min(c1.prices):.0f} zł) i {c2.source_id}:{c2.source_listing_id} ({c2.area_m2:.0f} m², "
                           f"{min(c2.prices):.0f} zł) to różne oferty")
                elif why.startswith("niejednoznaczne"):
                    why = "niejednoznaczne: kilku równie pasujących kandydatów z jednego portalu"
            reasons[why.split(":")[0].split(" (")[0].split(" o ")[0]].append({
                "a": f"{a.source_id}:{a.source_listing_id}", "b": f"{b.source_id}:{b.source_listing_id}",
                "areas": [a.area_m2, b.area_m2], "prices": [min(a.prices), min(b.prices)],
                "land_use": [a.land_use, b.land_use], "dist_m": round(dist) if dist is not None else None,
                "why": why})
    return {k: {"pairs": len(v), "examples": v[:examples]} for k, v in sorted(reasons.items(), key=lambda kv: -len(kv[1]))}


@dataclass(frozen=True)
class DedupQuality:
    precision: float
    recall: float
    true_pairs: int
    predicted_pairs: int
    correct_pairs: int


def evaluate(links: list[Link], truth: dict[tuple[str, str], str]) -> DedupQuality:
    """Precyzja / czułość na poziomie par ogłoszeń względem prawdy (np. z generatora)."""

    def pairs_of(groups: dict[str, list[tuple[str, str]]]) -> set[frozenset]:
        out = set()
        for members in groups.values():
            for a, b in combinations(sorted(members), 2):
                out.add(frozenset((a, b)))
        return out

    predicted: dict[str, list] = defaultdict(list)
    for l in links:
        predicted[l.property_key].append((l.source_id, l.source_listing_id))
    actual: dict[str, list] = defaultdict(list)
    for key, prop in truth.items():
        actual[prop].append(key)

    pred_pairs, true_pairs = pairs_of(predicted), pairs_of(actual)
    correct = len(pred_pairs & true_pairs)
    return DedupQuality(
        precision=correct / len(pred_pairs) if pred_pairs else 1.0,
        recall=correct / len(true_pairs) if true_pairs else 1.0,
        true_pairs=len(true_pairs),
        predicted_pairs=len(pred_pairs),
        correct_pairs=correct,
    )
