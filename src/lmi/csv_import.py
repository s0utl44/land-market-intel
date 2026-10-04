"""Parser i walidacja plików CSV z obserwacjami ogłoszeń.

Jeden plik = jedno źródło (source_id podawany przy imporcie, nie w pliku).
Format opisany w docs/csv_format.md.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REQUIRED_COLUMNS = (
    "source_listing_id",
    "observed_at",
    "municipality_teryt",
    "municipality_name",
    "area_m2",
    "price_pln",
)
OPTIONAL_COLUMNS = ("parcel_id", "lat", "lon", "land_use", "url", "title")

# Przybliżony prostokąt otaczający Polskę — odsiewa zamienione lat/lon i śmieci.
LAT_RANGE = (49.0, 55.0)
LON_RANGE = (14.0, 24.2)


@dataclass(frozen=True)
class Observation:
    source_listing_id: str
    observed_at: date
    municipality_teryt: str
    municipality_name: str
    area_m2: float
    price_pln: float
    parcel_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    land_use: str | None = None
    url: str | None = None
    title: str | None = None


@dataclass
class ParseResult:
    observations: list[Observation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows_in_file: int = 0
    sha256: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


class CsvFormatError(ValueError):
    """Błąd całego pliku (np. brak wymaganych kolumn)."""


def _num(value: str) -> float:
    # Akceptujemy polski zapis: "1 234,50" oraz zwykły "1234.50".
    cleaned = value.replace(" ", "").replace(" ", "").replace(",", ".")
    return float(cleaned)


def _opt(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_bytes(data: bytes) -> ParseResult:
    result = ParseResult(sha256=file_sha256(data))
    text = data.decode("utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvFormatError(f"Brak wymaganych kolumn: {', '.join(missing)}")

    seen: set[tuple[str, date]] = set()
    for line_no, row in enumerate(reader, start=2):  # 1 = nagłówek
        result.rows_in_file += 1
        try:
            obs = _parse_row(row)
        except ValueError as exc:
            result.errors.append(f"wiersz {line_no}: {exc}")
            continue
        key = (obs.source_listing_id, obs.observed_at)
        if key in seen:
            result.errors.append(
                f"wiersz {line_no}: duplikat ogłoszenia {obs.source_listing_id} "
                f"z dnia {obs.observed_at} w tym samym pliku"
            )
            continue
        seen.add(key)
        result.observations.append(obs)
    return result


def parse_file(path: str | Path) -> ParseResult:
    return parse_bytes(Path(path).read_bytes())


def _parse_row(row: dict[str, str | None]) -> Observation:
    def req(name: str) -> str:
        value = _opt(row.get(name))
        if value is None:
            raise ValueError(f"puste pole {name}")
        return value

    listing_id = req("source_listing_id")

    try:
        observed_at = date.fromisoformat(req("observed_at"))
    except ValueError as exc:
        if "puste pole" in str(exc):
            raise
        raise ValueError(f"observed_at musi być w formacie RRRR-MM-DD, jest {row.get('observed_at')!r}")

    teryt = req("municipality_teryt")
    if not (teryt.isdigit() and len(teryt) == 7):
        raise ValueError(f"municipality_teryt musi mieć 7 cyfr (TERYT gminy), jest {teryt!r}")

    try:
        area = _num(req("area_m2"))
        price = _num(req("price_pln"))
    except ValueError as exc:
        if "puste pole" in str(exc):
            raise
        raise ValueError("area_m2 i price_pln muszą być liczbami")
    if area <= 0:
        raise ValueError("area_m2 musi być > 0")
    if price <= 0:
        raise ValueError("price_pln musi być > 0")

    lat_raw, lon_raw = _opt(row.get("lat")), _opt(row.get("lon"))
    if (lat_raw is None) != (lon_raw is None):
        raise ValueError("lat i lon muszą być podane razem albo wcale")
    lat = lon = None
    if lat_raw is not None:
        try:
            lat, lon = _num(lat_raw), _num(lon_raw)
        except ValueError:
            raise ValueError("lat/lon muszą być liczbami")
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
            raise ValueError(f"współrzędne poza Polską: lat={lat}, lon={lon} (zamienione?)")

    return Observation(
        source_listing_id=listing_id,
        observed_at=observed_at,
        municipality_teryt=teryt,
        municipality_name=req("municipality_name"),
        area_m2=area,
        price_pln=price,
        parcel_id=_opt(row.get("parcel_id")),
        lat=lat,
        lon=lon,
        land_use=_opt(row.get("land_use")),
        url=_opt(row.get("url")),
        title=_opt(row.get("title")),
    )
