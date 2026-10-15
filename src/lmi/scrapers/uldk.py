"""ULDK (GUGiK): kod TERYT gminy dla punktu. https://uldk.gugik.gov.pl"""
from __future__ import annotations

import re

ULDK_URL = "https://uldk.gugik.gov.pl/?request=GetCommuneByXY&xy={lon:.6f},{lat:.6f},4326&result=teryt,commune"

# ostatnia cyfra TERYT gminy = rodzaj jednostki
COMMUNE_TYPES = {
    "1": "gm. miejska",
    "2": "gm. wiejska",
    "3": "gm. miejsko-wiejska",
    "4": "miasto",
    "5": "obszar wiejski",
    "8": "dzielnica",
    "9": "delegatura",
}


def parse_commune_response(body: str) -> tuple[str, str | None] | None:
    """'0\\n026401_1|Wrocław' -> ('0264011', 'Wrocław (gm. miejska)'). Brak wyniku -> None.

    Pierwsza linia to status (0 = OK). Nazwa bywa pusta — wtedy None.
    """
    lines = body.strip().splitlines()
    if len(lines) < 2 or lines[0].strip() != "0":
        return None
    fields = [f.strip() for f in lines[1].split("|")]
    m = re.fullmatch(r"(\d{6})_(\d)", fields[0])
    if not m:
        return None
    teryt = m.group(1) + m.group(2)
    name = next((f for f in fields[1:] if f), None)
    if name and m.group(2) in COMMUNE_TYPES:
        name = f"{name} ({COMMUNE_TYPES[m.group(2)]})"
    return teryt, name


def commune_url(lat: float, lon: float) -> str:
    return ULDK_URL.format(lat=lat, lon=lon)
