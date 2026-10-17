"""Parametry oferty wspólne dla portali: sprzedający, media, dojazd, ogrodzenie, okolica, negocjacja, aktualizacja.

Każdy parser strony oferty zwraca `detail["features"]` w jednym kształcie:
    {"seller": "prywatny" | "biuro" | "deweloper" | None, "negotiable": bool | None,
     "media": [...], "access": [...], "fence": bool | None, "vicinity": [...],
     "updated_at": "RRRR-MM-DD" | None, "params": {etykieta: wartość}}
`params` to surowe parametry z portalu (bez danych kontaktowych), reszta jest ujednolicona.
Typ sprzedającego to sama kategoria: nazw biur, nazwisk i telefonów nie zapisujemy.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

VERSION = 1

MEDIA = {"electricity": "prąd", "water": "woda", "gas": "gaz", "sewage": "kanalizacja", "phone": "telefon",
         "cesspool": "szambo", "internet": "internet", "septic": "szambo"}
ACCESS = {"asphalt": "asfaltowy", "hard_surfaced": "utwardzony", "soft_surfaced": "nieutwardzony",
          "field": "polny", "concrete": "betonowy"}
VICINITY = {"forest": "las", "lake": "jezioro", "sea": "morze", "open_terrain": "teren otwarty",
            "mountains": "góry", "river": "rzeka"}
# słowa z parametrów i opisów portali -> nazwy ujednolicone
MEDIA_WORDS = [("prąd", r"pr[aą]d|energi|elektry"), ("woda", r"\bwod[aęy]|wodoci"), ("gaz", r"\bgaz"),
               ("kanalizacja", r"kanaliz"), ("szambo", r"szamb"), ("telefon", r"telefon"),
               ("internet", r"internet|światłow")]
ACCESS_WORDS = [("asfaltowy", r"asfalt"), ("utwardzony", r"utwardzon|kostk|beton"), ("polny", r"poln|gruntow"),
                ("nieutwardzony", r"nieutwardz")]
# etykiety, których nie zapisujemy (kontakt, tożsamość ogłoszeniodawcy)
PERSONAL = re.compile(r"telefon|kontakt|e-?mail|imi[eę]|nazwisk|osoba|agent|opiekun|licencj|nip|nazwa", re.I)


def empty() -> dict:
    return {"seller": None, "negotiable": None, "media": [], "access": [], "fence": None, "vicinity": [],
            "updated_at": None, "params": {}, "v": VERSION}


def _words(text: str, table) -> list[str]:
    t = (text or "").lower()
    return [name for name, rx in table if re.search(rx, t)]


def from_params(params: dict, f: dict | None = None) -> dict:
    """Uzupełnia cechy z par etykieta: wartość (Gratka, Nieruchomości-online)."""
    f = f or empty()
    clean = {}
    for k, v in params.items():
        k = " ".join(str(k).split())[:60]
        if not k or PERSONAL.search(k):
            continue
        v = ", ".join(map(str, v)) if isinstance(v, list) else str(v if v is not None else "")
        clean[k] = " ".join(v.split())[:200]
    f["params"] = {**f.get("params", {}), **clean}
    for k, v in clean.items():
        lk = k.lower()
        if re.search(r"media|uzbrojen|instalac", lk) or (lk in {n for n, _ in MEDIA_WORDS} and v.lower() in ("tak", "jest")):
            found = _words(v, MEDIA_WORDS) if re.search(r"media|uzbrojen|instalac", lk) else _words(lk, MEDIA_WORDS)
            f["media"] = sorted(set(f["media"]) | set(found))
        elif re.search(r"dojazd|droga", lk):
            f["access"] = sorted(set(f["access"]) | set(_words(v, ACCESS_WORDS)))
        elif re.search(r"ogrodz", lk):
            f["fence"] = not re.search(r"\bnie\b|brak", v.lower())
        elif re.search(r"ogłoszeniodawc|oferta od|sprzedaj|typ oferty", lk):
            f["seller"] = seller_from_text(v) or f["seller"]
        elif re.search(r"negocj", lk):
            f["negotiable"] = not re.search(r"\bnie\b", v.lower())
        elif re.search(r"aktualiz", lk) and (d := pl_date(v)):
            f["updated_at"] = d.isoformat()
    return f


def seller_from_text(text: str | None) -> str | None:
    t = (text or "").lower()
    if re.search(r"dewelop", t):
        return "deweloper"
    if re.search(r"prywat|właściciel|wlasciciel|bezpośrednio|bez pośrednik", t):
        return "prywatny"
    if re.search(r"biur|agenc|pośredni|posredni|business|agency", t):
        return "biuro"
    return None


def pl_date(text: str | None) -> date | None:
    """'21.05.2026' albo '2026-05-21' -> date."""
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text or "")
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def relative_date(text: str | None, today: date) -> date | None:
    """'6 dni temu', 'wczoraj', 'dzisiaj', 'tydzień temu' -> date; 'ponad miesiąc temu' (zbyt ogólne) -> None."""
    t = (text or "").lower()
    if re.search(r"dzisiaj|dziś|godzin|minut", t):
        return today
    if "wczoraj" in t:
        return today - timedelta(days=1)
    if (m := re.search(r"(\d+)\s*dni", t)):
        return today - timedelta(days=int(m.group(1)))
    if (m := re.search(r"(\d+)?\s*tydz|(\d+)\s*tygod", t)) and "ponad" not in t:
        n = int(m.group(1) or m.group(2) or 1)
        return today - timedelta(days=7 * n)
    return None
