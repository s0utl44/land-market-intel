"""API Otodom dla zalogowanego użytkownika: historia ogłoszenia i statystyki (wyświetlenia, zapisania).

Te same zapytania wykonuje strona Otodom w przeglądarce zalogowanej osoby. Wymagają ciasteczka
sesji konta (plik wskazany przez LMI_OTODOM_COOKIE_FILE). Bez sesji API odpowiada "Forbidden Access".
Program się nie loguje: sesję tworzy człowiek w przeglądarce i kopiuje ciasteczko na serwer.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

API_URL = "https://www.otodom.pl/api/query"
PERSISTED_QUERIES = {
    "AdvertHistory": "246082d118c754f70b9a674ceab948d9c9f2cf884250d9d6423bb3537bae5fe3",
    "AdPageStatistics": "cb0834e87ca9c8f6d04f057ff053cf7f25db1c9ab7195e95f3cdd8dda5bea695",
}
DEFAULT_COOKIE_FILE = "data/otodom-cookie"


class SessionExpired(Exception):
    """Sesja konta Otodom wygasła albo ciasteczko jest nieprawidłowe."""


def load_cookie(path: str | None = None) -> str | None:
    p = Path(path or os.environ.get("LMI_OTODOM_COOKIE_FILE", DEFAULT_COOKIE_FILE))
    if not p.is_file():
        return None
    cookie = " ".join(p.read_text(encoding="utf-8", errors="replace").split())
    return cookie or None


def query_url(operation: str, variables: dict) -> str:
    return API_URL + "?" + urllib.parse.urlencode({
        "operationName": operation,
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps(
            {"persistedQuery": {"sha256Hash": PERSISTED_QUERIES[operation], "version": 1}}, separators=(",", ":")),
    })


def _check_errors(payload: dict) -> bool:
    """True, jeśli odpowiedź nadaje się do ponowienia (PersistedQueryNotFound). Wyjątek przy braku sesji."""
    errors = payload.get("errors") or []
    if not errors:
        return False
    text = json.dumps(errors)
    if "Forbidden" in text or "UNAUTHENTICATED" in text or "Unauthorized" in text:
        raise SessionExpired(text[:200])
    if "PERSISTED_QUERY_NOT_FOUND" in text or "PersistedQueryNotFound" in text:
        return True
    log.warning("otodom api: %s", text[:200])
    return False


def _date(v) -> str | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_history(payload: dict) -> list[dict] | None:
    """-> [{"date": "2013-12-30", "status": "ACTIVE", "price": 1100000.0 | None, "changes": [...]}]"""
    hist = ((payload.get("data") or {}).get("advertHistory") or {})
    entries = hist.get("entries")
    if entries is None:
        return None
    out = []
    for e in entries:
        price = (((e.get("price") or {}).get("value") or {}).get("value"))
        out.append({
            "date": _date(e.get("changedAt")),
            "status": e.get("status"),
            "price": float(price) if price is not None else None,
            "changes": list(e.get("changeType") or []),
        })
    out.sort(key=lambda x: x["date"] or "")
    return out


def parse_statistics(payload: dict) -> dict | None:
    st = (payload.get("data") or {}).get("adPageStatistics")
    if not st:
        return None
    return {"views": st.get("viewsCount"), "saved": st.get("savedCount")}


class OtodomApi:
    """`get(url, headers) -> str`, np. PoliteClient.get."""

    def __init__(self, get: Callable[..., str], cookie: str):
        self._get = get
        self._headers = {"Cookie": cookie, "Accept": "application/json", "Referer": "https://www.otodom.pl/"}
        self.alive = True

    def _call(self, operation: str, variables: dict) -> dict | None:
        for _ in range(2):  # PersistedQueryNotFound bywa chwilowe
            payload = json.loads(self._get(query_url(operation, variables), self._headers))
            if not _check_errors(payload):
                return payload
        return None

    def history(self, ad_id: str) -> list[dict] | None:
        try:
            payload = self._call("AdvertHistory", {"adID": str(ad_id)})
        except SessionExpired:
            self.alive = False
            raise
        return parse_history(payload) if payload else None

    def statistics(self, ad_id: str, listed_from: str | None) -> dict | None:
        variables = {"adID": str(ad_id)}
        if listed_from:
            variables["from"] = f"{listed_from}T00:00:00Z"
        try:
            payload = self._call("AdPageStatistics", variables)
        except SessionExpired:
            self.alive = False
            raise
        return parse_statistics(payload) if payload else None
