"""Ceny transakcyjne z Rejestru Cen Nieruchomości (RCN) — bezpłatna usługa WFS geoportalu GUGiK.

Warstwa ms:dzialki: jeden rekord = jedna działka w jednej transakcji (akcie notarialnym).
Pobieramy wszystkie rodzaje transakcji z województwa (bez geometrii), miesiąc po miesiącu,
a transakcje gruntowe wyznacza widok mart.rcn_land_transactions: tylko takie, w których każda
działka jest nieruchomością gruntową niezabudowaną, w całości (udział 1/1), na wolnym rynku
lub w przetargu. Transakcje mieszane (dom + działka, lokal z udziałem w gruncie) pomijamy,
bo ich cena nie dotyczy samego gruntu.

Nie zapisujemy nazwisk notariuszy (DOK_TWORCA) ani pełnych adresów; strony transakcji
są w RCN tylko kategoriami (osoba fizyczna / prawna).
"""
from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from .scrapers.http import PoliteClient

log = logging.getLogger(__name__)

WFS = "https://mapy.geoportal.gov.pl/wss/service/rcn"
LAYER = "ms:dzialki"
START = date(2020, 1, 1)        # pierwsze pobranie: od tego dnia (pełna historia z ostatnich lat)
REFRESH_BACK_DAYS = 120         # starostwa dopisują akty z opóźnieniem: odświeżamy ostatnie miesiące
PAGE = 1000
FIELDS = ["TERYT", "TRAN_LOKALNY_ID_IIP", "TRAN_RODZAJ_TRANS", "TRAN_RODZAJ_RYNKU", "TRAN_SPRZEDAJACY",
          "TRAN_KUPUJACY", "TRAN_CENA_BRUTTO", "DOK_DATA", "NIER_RODZAJ", "NIER_PRAWO", "NIER_UDZIAL",
          "NIER_CENA_BRUTTO", "DZI_ID_DZIALKI", "DZI_PRZEZN_WMPZP", "DZI_POW_EWID", "DZI_SPOSOB_UZYT",
          "DZI_CENA_BRUTTO", "DZI_ADRES"]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# 30 powiatów województwa dolnośląskiego (26 ziemskich + 4 miasta na prawach powiatu)
POWIATY_02 = [f"02{n:02d}" for n in range(1, 27)] + ["0261", "0262", "0264", "0265"]


def _filter(teryt_prefix: str, since: date | None, until: date | None) -> str:
    """since=None i until=None: akty BEZ daty (filtr po dacie by je pominął)."""
    teryt = ('<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!"><fes:ValueReference>TERYT</fes:ValueReference>'
             f'<fes:Literal>{teryt_prefix}*</fes:Literal></fes:PropertyIsLike>')
    if since is None and until is None:
        when = '<fes:PropertyIsNull><fes:ValueReference>DOK_DATA</fes:ValueReference></fes:PropertyIsNull>'
    else:
        when = ('<fes:PropertyIsGreaterThanOrEqualTo><fes:ValueReference>DOK_DATA</fes:ValueReference>'
                f'<fes:Literal>{since.isoformat()}</fes:Literal></fes:PropertyIsGreaterThanOrEqualTo>'
                '<fes:PropertyIsLessThan><fes:ValueReference>DOK_DATA</fes:ValueReference>'
                f'<fes:Literal>{until.isoformat()}</fes:Literal></fes:PropertyIsLessThan>')
    return f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:And>{teryt}{when}</fes:And></fes:Filter>'


def page_url(teryt_prefix: str, since: date | None, until: date | None, start: int, count: int = PAGE,
             plain: bool = False) -> str:
    """plain=True: bez wyboru pól i sortowania (zapytanie awaryjne, gdy zwykłe pomija rekordy)."""
    params = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
              "FILTER": _filter(teryt_prefix, since, until), "COUNT": str(count), "STARTINDEX": str(start)}
    if not plain:
        params["PROPERTYNAME"] = ",".join(FIELDS)   # bez geometrii: kilka razy mniejsze odpowiedzi
        params["SORTBY"] = "gid"
    return WFS + "?" + urllib.parse.urlencode(params)


def hits_url(teryt_prefix: str, since: date | None, until: date | None) -> str:
    return WFS + "?" + urllib.parse.urlencode({
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
        "RESULTTYPE": "hits", "FILTER": _filter(teryt_prefix, since, until),
    })


def parse_hits(xml: str) -> int:
    root = ET.fromstring(xml)
    if _local(root.tag) == "ExceptionReport":
        raise ValueError("WFS: " + " ".join((e.text or "") for e in root.iter() if _local(e.tag) == "ExceptionText"))
    n = root.get("numberMatched")
    if n is None or not n.isdigit():
        raise ValueError(f"WFS: brak numberMatched ({n!r})")
    return int(n)


class Incomplete(Exception):
    """Pobrano mniej rekordów, niż usługa deklaruje — nie zapisujemy okresu jako kompletnego."""


def parse_features(xml: str) -> list[dict]:
    """GML -> [{pole: tekst}]; pola czasu (gml:TimeInstant/timePosition) spłaszczone do daty."""
    root = ET.fromstring(xml)
    if _local(root.tag) == "ExceptionReport":
        msg = " ".join((e.text or "").strip() for e in root.iter() if _local(e.tag) == "ExceptionText")
        raise ValueError(f"WFS: {msg or 'błąd usługi'}")
    out = []
    for m in root.iter():
        if _local(m.tag) not in ("member", "featureMember"):
            continue
        obj = next(iter(m), None)
        if obj is None:
            continue
        rec = {}
        for c in obj:
            if len(c) == 0:
                rec[_local(c.tag)] = (c.text or "").strip()
            else:  # np. DOK_DATA -> gml:TimeInstant -> gml:timePosition
                pos = next((e.text for e in c.iter() if _local(e.tag) == "timePosition" and e.text), None)
                if pos:
                    rec[_local(c.tag)] = pos.strip()
        out.append(rec)
    return out


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _day(v: str | None) -> date | None:
    try:
        return date.fromisoformat((v or "")[:10])
    except ValueError:
        return None


def gmina_teryt(parcel_id: str) -> str | None:
    """'022302_2.0012.401/2' -> '0223022' (TERYT gminy z rodzajem, jak w ULDK)."""
    head = (parcel_id or "").split(".", 1)[0]
    if len(head) == 8 and head[6] == "_" and head[:6].isdigit() and head[7].isdigit():
        return head[:6] + head[7]
    return None


def locality(address: str | None) -> str | None:
    """'MSC:Domaszczyn;UL:Leśna;NR_PORZ:2D' -> 'Domaszczyn' (bez ulicy i numeru)."""
    for part in (address or "").split(";"):
        if part.startswith("MSC:"):
            return part[4:].strip() or None
    return None


def to_row(rec: dict) -> tuple | None:
    tx, parcel = rec.get("TRAN_LOKALNY_ID_IIP"), rec.get("DZI_ID_DZIALKI")
    if not tx or not parcel:
        return None
    return (
        tx, parcel, gmina_teryt(parcel), _day(rec.get("DOK_DATA")),
        rec.get("TRAN_RODZAJ_TRANS") or None, rec.get("TRAN_RODZAJ_RYNKU") or None,
        rec.get("TRAN_SPRZEDAJACY") or None, rec.get("TRAN_KUPUJACY") or None,
        # rodzaj i udział są częścią klucza (jeden akt może obejmować kilka lokali na tej samej działce),
        # więc zamiast NULL pusty tekst
        _num(rec.get("TRAN_CENA_BRUTTO")), rec.get("NIER_RODZAJ") or "", rec.get("NIER_PRAWO") or None,
        rec.get("NIER_UDZIAL") or "", _num(rec.get("NIER_CENA_BRUTTO")),
        rec.get("DZI_PRZEZN_WMPZP") or None, _num(rec.get("DZI_POW_EWID")), rec.get("DZI_SPOSOB_UZYT") or None,
        _num(rec.get("DZI_CENA_BRUTTO")), locality(rec.get("DZI_ADRES")),
    )


UPSERT = """
INSERT INTO scrape.rcn_parcels (tx_id, parcel_id, gmina_teryt, doc_date, tran_type, market, seller_type, buyer_type,
    tran_price, nier_type, nier_right, share, nier_price, mpzp, area_m2, land_use, parcel_price, locality)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (tx_id, parcel_id, nier_type, share) DO UPDATE SET
    gmina_teryt = EXCLUDED.gmina_teryt, doc_date = EXCLUDED.doc_date, tran_type = EXCLUDED.tran_type,
    market = EXCLUDED.market, seller_type = EXCLUDED.seller_type, buyer_type = EXCLUDED.buyer_type,
    tran_price = EXCLUDED.tran_price, nier_right = EXCLUDED.nier_right, nier_price = EXCLUDED.nier_price, mpzp = EXCLUDED.mpzp, area_m2 = EXCLUDED.area_m2,
    land_use = EXCLUDED.land_use, parcel_price = EXCLUDED.parcel_price, locality = EXCLUDED.locality,
    fetched_at = now()
"""


def months(since: date, until: date):
    d = since.replace(day=1)
    while d < until:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(d, since), min(nxt, until)
        d = nxt


def _powiaty(prefix: str) -> list[str]:
    return POWIATY_02 if prefix == "02" else [f"{prefix}{n:02d}" for n in list(range(1, 41)) + list(range(61, 66))]


def _pages(get, prefix: str, since: date | None, until: date | None, matched: int,
           plain: bool = False) -> list[dict]:
    recs: list[dict] = []
    start = 0
    while len(recs) < matched:
        page = parse_features(get(page_url(prefix, since, until, start, plain=plain)))
        if not page:
            break
        recs.extend(page)
        start += len(page)
    return recs


def _key(rec: dict) -> tuple:
    return (rec.get("TRAN_LOKALNY_ID_IIP"), rec.get("DZI_ID_DZIALKI"), rec.get("NIER_RODZAJ") or "",
            rec.get("NIER_UDZIAL") or "")


def _unique(recs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in recs:
        k = _key(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _fetch(get, prefix: str, since: date | None, until: date | None) -> tuple[list[dict], int, list[str]]:
    """Rekordy okresu (bez powtórzeń) + liczba zadeklarowana przez usługę + luki.

    Gdy usługa przestaje oddawać kolejne strony, zapytanie jest dzielone: okres na połowy (do jednego dnia),
    potem województwo na powiaty. Gdy nawet jeden dzień w jednym powiecie nie daje wszystkich rekordów,
    próbujemy zapytania bez wyboru pól i sortowania; jeśli i to nie pomoże, to błąd samej usługi —
    zapisujemy lukę (widoczną w dzienniku i raporcie) i jedziemy dalej, zamiast blokować cały import."""
    matched = parse_hits(get(hits_url(prefix, since, until)))
    if matched == 0:
        return [], 0, []
    recs = _unique(_pages(get, prefix, since, until, matched))
    if len(recs) >= matched:
        return recs, matched, []
    log.info("rcn: %s %s–%s: usługa oddała %d z %d, dzielę zapytanie", prefix, since, until, len(recs), matched)
    if since is not None and until is not None and (until - since).days > 1:
        mid = since + (until - since) // 2
        parts = [_fetch(get, prefix, since, mid), _fetch(get, prefix, mid, until)]
    elif len(prefix) == 2:
        parts = [_fetch(get, pw, since, until) for pw in _powiaty(prefix)]
    else:
        plain = _unique(_pages(get, prefix, since, until, matched, plain=True))
        best = plain if len(plain) > len(recs) else recs
        if len(best) >= matched:
            return best, matched, []
        gap = f"{prefix} {since or 'bez daty'}–{until or ''}: brak {matched - len(best)} z {matched}"
        log.warning("rcn: luka w usłudze: %s", gap)
        return best, matched, [gap]
    got = _unique([r for part, _, _ in parts for r in part])
    gaps = [g for _, _, gs in parts for g in gs]
    # nadmiar bywa (akt z dnia granicy liczony w obu częściach) i znika przy usuwaniu powtórzeń;
    # brak jest dopuszczalny tylko wtedy, gdy wynika z zapisanych luk usługi
    if len(got) < matched and not gaps:
        raise Incomplete(f"{prefix} {since}–{until}: części dały {len(got)} rekordów, usługa deklaruje {matched}")
    return got, matched, gaps


def fetch_period(get, teryt_prefix: str, since: date | None,
                 until: date | None) -> tuple[list[tuple], int, list[str]]:
    """Wszystkie rekordy okresu z kontrolą kompletności. Zwraca (wiersze, liczba w usłudze, luki usługi)."""
    recs_all, matched, gaps = _fetch(get, teryt_prefix, since, until)
    rows = [r for r in map(to_row, recs_all) if r]
    log.info("rcn: %s – %s: %d rekordów (usługa: %d, bez numeru transakcji/działki: %d%s)",
             since or "bez daty", until or "", len(rows), matched, len(recs_all) - len(rows),
             f", luki: {len(gaps)}" if gaps else "")
    return rows, matched, gaps


def refresh(conn, get=None, teryt_prefix: str = "02", today: date | None = None,
            since: date | None = None) -> int:
    """Dociąga akty od ostatniego znanego (minus REFRESH_BACK_DAYS) albo od START. Zwraca liczbę rekordów."""
    today = today or date.today()
    get = get or PoliteClient(min_delay=1.0, max_delay=2.0, timeout=180).get  # usługa publiczna, krótsze przerwy
    if since is None:
        last = conn.execute("SELECT max(doc_date) FROM scrape.rcn_parcels WHERE gmina_teryt LIKE %s",
                            (teryt_prefix + "%",)).fetchone()[0]
        since = max(START, last - timedelta(days=REFRESH_BACK_DAYS)) if last else START
    total = 0
    periods = list(months(since, today + timedelta(days=1))) + [(None, None)]  # + akty bez daty
    for a, b in periods:
        rows, matched, gaps = fetch_period(get, teryt_prefix, a, b)
        with conn.cursor() as cur:
            cur.executemany(UPSERT, rows)
            cur.execute("""INSERT INTO scrape.rcn_fetch_log (teryt_prefix, period_start, period_end, matched, saved, gaps)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (teryt_prefix, a, b, matched, len(rows), "; ".join(gaps) or None))
        conn.commit()  # miesiąc po miesiącu: przerwane pobieranie nie traci wyników
        total += len(rows)
    log.info("rcn: zapisano %d rekordów (od %s)", total, since)
    return total


def coverage(conn, get=None, powiaty: list[str] | None = None, since: date = START) -> list[dict]:
    """Kompletność per powiat: rekordy w usłudze (od `since`) vs w bazie, transakcje i transakcje gruntowe."""
    get = get or PoliteClient(min_delay=1.0, max_delay=2.0, timeout=180).get
    today = date.today() + timedelta(days=1)
    out = []
    for pw in powiaty or POWIATY_02:
        service = parse_hits(get(hits_url(pw, since, today)))
        db_rows, db_tx = conn.execute(
            """SELECT count(*), count(DISTINCT tx_id) FROM scrape.rcn_parcels
               WHERE left(parcel_id, 4) = %s AND doc_date >= %s""", (pw, since)).fetchone()
        land = conn.execute("""SELECT count(*) FROM mart.rcn_land_transactions
                               WHERE left(gmina_teryt, 4) = %s AND doc_date >= %s""", (pw, since)).fetchone()[0]
        out.append({"powiat": pw, "service": service, "db_rows": db_rows, "db_tx": db_tx, "land_tx": land})
    return out
