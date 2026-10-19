"""Pozwolenia na budowę z rejestru GUNB (RWDZ: wnioski i decyzje w sprawach budowlanych).

Plik dla województwa: https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_dolnoslaskie.zip (CSV, od 2016).
Jeden wiersz = jedna działka we wniosku/decyzji; pozwolenie liczymy raz (numer_gunb). Gmina z jednostki
ewidencyjnej działki (jak w RCN: miasto/obszar wiejski gminy miejsko-wiejskiej -> gmina), a gdy jej brak,
z kodu TERC adresu inwestycji.

Nie zapisujemy danych osobowych: nazwy inwestora, adresu, ulicy ani projektanta (imię, nazwisko, uprawnienia).
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime

from .rcn import gmina_teryt

log = logging.getLogger(__name__)

URL = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_{region}.zip"
BATCH = 5000
SINGLE_FAMILY = "Budynek mieszkalny jednorodzinny"


def _date(v: str | None) -> date | None:
    v = (v or "").strip()[:10]
    try:
        return datetime.strptime(v, "%Y-%m-%d").date() if v else None
    except ValueError:
        return None


def _num(v: str | None) -> float | None:
    try:
        return float((v or "").replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def gmina_of(unit: str | None, terc: str | None) -> str | None:
    """'020104_5' (jednostka ewidencyjna) -> '0201043'; bez jednostki: TERC adresu (7 cyfr)."""
    if unit and (t := gmina_teryt(unit.strip() + ".0")):
        return t
    terc = (terc or "").strip()
    if len(terc) == 7 and terc.isdigit():
        return gmina_teryt(f"{terc[:6]}_{terc[6]}.0")
    return None


def rows(text_stream, teryt_prefix: str = "02"):
    """Wiersze do zapisu: (numer_gunb, działka, gmina, data_wniosku, data_decyzji, rodzaj, kategoria, kubatura)."""
    head_line = text_stream.readline()
    delim = ";" if head_line.count(";") > head_line.count(",") else ","
    head = next(csv.reader([head_line], delimiter=delim))
    idx = {}
    for i, name in enumerate(head):
        idx.setdefault(name.strip().lower(), i)        # kolumna "cecha" występuje dwa razy: bierzemy pierwszą

    def col(r, name):
        i = idx.get(name)
        return r[i] if i is not None and i < len(r) else ""

    for r in csv.reader(text_stream, delimiter=delim):
        number = col(r, "numer_gunb").strip()
        if not number:
            continue
        gmina = gmina_of(col(r, "jednosta_numer_ew"), col(r, "terc"))
        if not gmina or not gmina.startswith(teryt_prefix):
            continue
        parcel = "|".join(x.strip() for x in (col(r, "jednosta_numer_ew"), col(r, "obreb_numer"), col(r, "numer_dzialki")))
        yield (number, parcel, gmina, _date(col(r, "data_wplywu_wniosku")), _date(col(r, "data_wydania_decyzji")),
               col(r, "rodzaj_inwestycji").strip()[:120] or None, col(r, "kategoria").strip()[:10] or None,
               _num(col(r, "kubatura")))


INSERT = """INSERT INTO scrape.gunb_permits (numer_gunb, parcel, gmina_teryt, filed_on, decided_on, kind, category, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING"""


def load(conn, zip_bytes: bytes, teryt_prefix: str = "02") -> int:
    """Zastępuje całą zawartość rejestru plikiem GUNB (jedna transakcja: strona nie widzi pustej tabeli)."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    n = 0
    with conn.transaction():
        conn.execute("DELETE FROM scrape.gunb_permits")
        with z.open(name) as raw, conn.cursor() as cur:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            batch = []
            for row in rows(text, teryt_prefix):
                batch.append(row)
                if len(batch) >= BATCH:
                    cur.executemany(INSERT, batch)
                    n += len(batch)
                    batch.clear()
                    if n % 50000 == 0:
                        log.info("gunb: zapisano %d wierszy", n)
            if batch:
                cur.executemany(INSERT, batch)
                n += len(batch)
        conn.execute("""INSERT INTO scrape.gunb_fetch_log (rows, permits)
                        SELECT %s, count(DISTINCT numer_gunb) FROM scrape.gunb_permits""", (n,))
        conn.execute("SELECT scrape.fix_gmina_codes()")   # stare kody gmin -> aktualne (db/init/020)
        conn.execute("REFRESH MATERIALIZED VIEW mart.gunb_permits")
    conn.commit()
    return n


def refresh(conn, get=None, region: str = "dolnoslaskie", teryt_prefix: str = "02") -> int:
    """Pobiera plik województwa (ok. 25 MB) i wczytuje go od nowa."""
    if get is None:
        import urllib.request

        def get(url):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (radar-dzialek; dane publiczne)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
    url = URL.format(region=region)
    log.info("gunb: pobieram %s", url)
    data = get(url)
    n = load(conn, data, teryt_prefix)
    log.info("gunb: wczytano %d wierszy", n)
    return n
