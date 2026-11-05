"""Eksport prywatnych działek do Zimnych (aplikacja Leady, 5.11 – decyzja użytkownika: zimne telefony na działki).

Po porannym przebiegu Radaru zapisujemy do pliku JSON aktywne działki od PRYWATNYCH sprzedających (jak filtr „prywatny”
w Radarze: właściciel potwierdzony przez Adresowo / Gratkę albo „prywatny” z Otodomu bez biura na innym portalu) z całego
województwa. Plik trafia do katalogu danych Zimnych (/opt/leady-dane) – Zimne wczytują go same. Bez danych osobowych:
Radar nie zapisuje telefonów, imion ani opisów (docs/legal_checklist.md); numer agent wkleja w Zimnych sam, jak przy mieszkaniach.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)
WOJEWODZTWO = os.environ.get("LMI_ZIMNE_TERYT", "02")          # dolnośląskie
POLA = ("id", "price", "area", "ppm2", "land_use", "url", "source", "sources", "listing_keys", "offers", "municipality", "teryt",
        "first_seen", "listed_at", "pushed_up_at", "start_date", "age_days", "price_change", "precise", "features")


def _json(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def prywatne_dzialki(limit: int = 50000) -> list[dict]:
    from . import web
    params = {"me": "", "limit": limit, "seller": "prywatny", "woj": WOJEWODZTWO + "%"}
    rows = web._offers("o.municipality_teryt LIKE %(woj)s", ["active", web.seller_where("prywatny")], params, "newest")
    return [{k: r.get(k) for k in POLA} for r in rows]


def eksport(plik: str) -> int:
    dzialki = prywatne_dzialki()
    cel = Path(plik)
    tmp = cel.with_suffix(cel.suffix + ".tmp")
    tmp.write_text(json.dumps({"utworzono": datetime.now().astimezone().isoformat(timespec="seconds"), "dzialki": dzialki},
                              ensure_ascii=False, default=_json))
    tmp.replace(cel)                                       # zamiana naraz – Zimne nie przeczytają połowy pliku
    log.info("zimne: %d prywatnych działek → %s", len(dzialki), cel)
    return len(dzialki)
