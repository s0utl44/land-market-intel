"""Generator danych syntetycznych: 3 fikcyjne gminy o różnej dynamice rynku.

Każda "prawdziwa" działka może być wystawiona na kilku portalach (z szumem w
współrzędnych, powierzchni i cenie), dzięki czemu można zmierzyć jakość deduplikacji.
Kody TERYT zaczynają się od 99 — taki kod województwa nie istnieje, więc dane
syntetyczne nie pomylą się z prawdziwymi.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Region:
    teryt: str
    name: str
    center: tuple[float, float]
    radius_km: float
    initial_stock: int
    arrivals_per_week: float
    weekly_sale_hazard: float
    weekly_price_drift: float
    weekly_cut_prob: float
    base_price_per_m2: float


REGIONS = (
    Region("9900011", "Syntetyczna Rozwojowa", (52.10, 21.20), 6, 90, 9, 0.09, 0.004, 0.01, 260),
    Region("9900022", "Syntetyczna Stabilna", (51.10, 17.20), 7, 150, 6, 0.04, 0.001, 0.03, 180),
    Region("9900033", "Syntetyczna Zastój", (53.40, 19.80), 8, 280, 5, 0.015, -0.002, 0.06, 90),
)

# prawdopodobieństwo, że działka jest wystawiona na danym portalu
SOURCES = {"portal_a": 0.8, "portal_b": 0.5, "portal_c": 0.3}

CSV_COLUMNS = [
    "source_listing_id", "observed_at", "municipality_teryt", "municipality_name",
    "parcel_id", "lat", "lon", "area_m2", "price_pln", "land_use", "url", "title",
    "listed_at", "pushed_up_at",
]


def _offset(center: tuple[float, float], dx_m: float, dy_m: float) -> tuple[float, float]:
    lat = center[0] + dy_m / 111_320.0
    lon = center[1] + dx_m / (111_320.0 * math.cos(math.radians(center[0])))
    return lat, lon


def make_regions(n: int, seed: int = 0) -> tuple[Region, ...]:
    """Więcej fikcyjnych gmin o losowej dynamice (do podglądu strony). Część jest celowo mała."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        heat = rng.random()  # 0 = zastój, 1 = gorący rynek
        small = rng.random() < 0.3
        out.append(Region(
            teryt=f"99{i + 1:04d}{rng.choice('123')}",
            name=f"Gmina Przykładowa {i + 1}",
            center=(50.6 + rng.random() * 1.2, 15.2 + rng.random() * 2.6),
            radius_km=rng.uniform(3, 8),
            initial_stock=rng.randint(2, 8) if small else rng.randint(30, 250),
            arrivals_per_week=rng.uniform(0.2, 1) if small else rng.uniform(2, 10),
            weekly_sale_hazard=0.01 + 0.09 * heat,
            weekly_price_drift=-0.002 + 0.006 * heat,
            weekly_cut_prob=0.07 - 0.06 * heat,
            base_price_per_m2=rng.uniform(60, 420),
        ))
    return tuple(out)


def generate(out_dir: str | Path, weeks: int = 26, seed: int = 42,
             start: date = date(2026, 1, 5), regions: tuple[Region, ...] = REGIONS) -> dict[str, Path]:
    """Zapisuje portal_*.csv oraz ground_truth.csv. Zwraca ścieżki plików."""
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[dict]] = {s: [] for s in SOURCES}
    truth: list[dict] = []
    listing_counter = {s: 0 for s in SOURCES}
    prop_counter = 0
    # jeden dzień pobrania na tydzień, wspólny dla wszystkich gmin (jak w prawdziwym przebiegu)
    scrape_days = [start + timedelta(weeks=w, days=random.Random(seed + w).randint(0, 1)) for w in range(weeks)]
    # daty dodania / podbicia z osobnego generatora, żeby nie zmieniać reszty danych
    date_rng = random.Random(seed + 7919)

    for region in regions:

        def new_property(week: int) -> dict:
            nonlocal prop_counter
            prop_counter += 1
            r = region.radius_km * 1000 * math.sqrt(rng.random())
            phi = rng.random() * 2 * math.pi
            lat, lon = _offset(region.center, r * math.cos(phi), r * math.sin(phi))
            area = round(rng.lognormvariate(math.log(1200), 0.5))
            # nowe oferty wchodzą po bieżącym poziomie cen rynku, nie po cenie z tygodnia 0
            market_level = (1 + region.weekly_price_drift) ** week
            ppm2 = region.base_price_per_m2 * market_level * rng.lognormvariate(0, 0.25)
            parcel = f"{region.teryt[:6]}_{region.teryt[6]}.{rng.randint(1, 30):04d}.{rng.randint(1, 2500)}"
            if rng.random() < 0.3:
                parcel += f"/{rng.randint(1, 9)}"
            prop = {
                "id": f"T{prop_counter:05d}", "lat": lat, "lon": lon, "area": area,
                "price": round(area * ppm2, -3), "parcel": parcel, "start": week,
                "land_use": rng.choice(["budowlana", "budowlana", "budowlana", "rolna", "rekreacyjna"]),
                "listings": {},
            }
            if week == 0:  # oferty sprzed startu obserwacji: wiek z rozkładu wykładniczego
                age_days = int(date_rng.expovariate(region.weekly_sale_hazard) * 7)
                prop["listed"] = scrape_days[0] - timedelta(days=age_days)
            else:
                prop["listed"] = scrape_days[week] - timedelta(days=date_rng.randint(0, 6))
            prop["pushed"] = None
            if date_rng.random() < 0.15:
                pw = week + date_rng.randint(2, 10)
                prop["pushed"] = scrape_days[pw] if pw < weeks else None
            for src, p in SOURCES.items():
                if rng.random() < p:
                    prop["listings"][src] = None
            if not prop["listings"]:
                prop["listings"][rng.choice(list(SOURCES))] = None
            for src in prop["listings"]:
                listing_counter[src] += 1
                prop["listings"][src] = {
                    "id": f"{src[-1].upper()}{listing_counter[src]:06d}",
                    "jitter": (rng.gauss(0, 20), rng.gauss(0, 20)),
                    "has_coords": rng.random() < 0.9,
                    "has_parcel": rng.random() < 0.4,
                    "area_rounded": rng.random() < 0.3,
                    "price_mult": 1.0 if rng.random() < 0.7 else 1 + rng.uniform(-0.01, 0.01),
                    "lag": 0 if rng.random() < 0.8 else 1,
                }
                truth.append({"source_id": src, "source_listing_id": prop["listings"][src]["id"],
                              "true_property_id": prop["id"]})
            return prop

        active = [new_property(0) for _ in range(region.initial_stock)]
        for week in range(weeks):
            if week > 0:
                for _ in range(_poisson(rng, region.arrivals_per_week)):
                    active.append(new_property(week))
            observed_at = scrape_days[week]
            still_active = []
            for prop in active:
                # ceny ofertowe zmieniają się skokowo (obniżki); trend rynku widać
                # w cenach NOWYCH ofert, które wchodzą po bieżącym poziomie rynku
                if week > prop["start"]:
                    if rng.random() < region.weekly_cut_prob:
                        prop["price"] *= 1 - rng.uniform(0.03, 0.10)
                for src, lst in prop["listings"].items():
                    if week < prop["start"] + lst["lag"]:
                        continue
                    lat, lon = _offset((prop["lat"], prop["lon"]), *lst["jitter"])
                    area = round(prop["area"], -1) if lst["area_rounded"] else prop["area"]
                    rows[src].append({
                        "source_listing_id": lst["id"],
                        "observed_at": observed_at.isoformat(),
                        "municipality_teryt": region.teryt,
                        "municipality_name": region.name,
                        "parcel_id": prop["parcel"] if lst["has_parcel"] else "",
                        "lat": f"{lat:.6f}" if lst["has_coords"] else "",
                        "lon": f"{lon:.6f}" if lst["has_coords"] else "",
                        "area_m2": area,
                        "price_pln": round(prop["price"] * lst["price_mult"], -2),
                        "land_use": prop["land_use"],
                        "url": f"https://example.invalid/{src}/{lst['id']}",
                        "title": f"Działka {prop['land_use']} {area} m²",
                        "listed_at": prop["listed"].isoformat(),
                        "pushed_up_at": prop["pushed"].isoformat()
                        if prop["pushed"] and prop["pushed"] <= observed_at else "",
                    })
                if rng.random() >= region.weekly_sale_hazard:
                    still_active.append(prop)
            active = still_active

    paths: dict[str, Path] = {}
    for src, src_rows in rows.items():
        path = out / f"{src}.csv"
        _write_csv(path, CSV_COLUMNS, src_rows)
        paths[src] = path
    # ogłoszenie z opóźnieniem mogło nigdy się nie pojawić (działka sprzedana wcześniej)
    observed = {(src, r["source_listing_id"]) for src, src_rows in rows.items() for r in src_rows}
    truth = [t for t in truth if (t["source_id"], t["source_listing_id"]) in observed]
    truth_path = out / "ground_truth.csv"
    _write_csv(truth_path, ["source_id", "source_listing_id", "true_property_id"], truth)
    paths["ground_truth"] = truth_path
    return paths


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def load_ground_truth(path: str | Path) -> dict[tuple[str, str], str]:
    with Path(path).open(encoding="utf-8") as f:
        return {(r["source_id"], r["source_listing_id"]): r["true_property_id"] for r in csv.DictReader(f)}
