"""Deduplikacja: łączenie ogłoszeń (z różnych portali lub powtórzonych) w jedną nieruchomość.

Reguły (od najmocniejszej):
  1. parcel_id   — ten sam znormalizowany identyfikator działki.
  2. location    — odległość <= max_distance_m i różnica powierzchni <= location_area_tol.
  3. price_area  — tylko gdy któreś ogłoszenie nie ma współrzędnych: ta sama gmina,
                   pierwsze pojawienie się w odstępie <= price_area_max_start_gap_days,
                   powierzchnia <= price_area_area_tol i jakakolwiek para cen
                   <= price_area_price_tol. To słaby sygnał, więc para jest akceptowana
                   tylko gdy jest jednoznaczna (ogłoszenie bez współrzędnych ma dokładnie
                   jednego kandydata z danego źródła).
Dwa ogłoszenia z RÓŻNYMI parcel_id nigdy nie są łączone (konflikt).
Łączenie jest przechodnie (union-find), więc A~B i B~C daje jedną nieruchomość A,B,C.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Iterable

ALGORITHM_VERSION = "dedup-v1"

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
    price_area_price_tol: float = 0.005
    price_area_max_start_gap_days: int = 14

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
                if _parcel_conflict(a, b):
                    continue
                if (
                    _rel_diff(a.area_m2, b.area_m2) <= params.location_area_tol
                    and haversine_m(a.lat, a.lon, b.lat, b.lon) <= params.max_distance_m
                ):
                    pairs.append((i, j, "location"))

    # 3. price_area — tylko gdy brakuje współrzędnych po którejś stronie
    by_muni: dict[str, list[int]] = defaultdict(list)
    for i, l in enumerate(listings):
        by_muni[l.municipality_teryt].append(i)
    price_area: set[tuple[int, int]] = set()
    for idx in by_muni.values():
        for i in (i for i in idx if not listings[i].has_coords):
            a = listings[i]
            per_source: dict[str, list[int]] = defaultdict(list)
            for j in idx:
                b = listings[j]
                if j == i or _parcel_conflict(a, b):
                    continue
                if (
                    abs((a.first_seen - b.first_seen).days) <= params.price_area_max_start_gap_days
                    and _rel_diff(a.area_m2, b.area_m2) <= params.price_area_area_tol
                    and _prices_close(a, b, params.price_area_price_tol)
                ):
                    per_source[b.source_id].append(j)
            for candidates in per_source.values():
                if len(candidates) == 1:  # niejednoznaczne dopasowania odrzucamy
                    j = candidates[0]
                    price_area.add((min(i, j), max(i, j)))
    pairs.extend((i, j, "price_area") for i, j in sorted(price_area))
    return pairs


def deduplicate(listings: list[Listing], params: DedupParams | None = None) -> list[Link]:
    params = params or DedupParams()
    uf = _UnionFind(len(listings))
    best_method: dict[int, str] = {}

    for i, j, method in candidate_pairs(listings, params):
        uf.union(i, j)
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
