"""Liczniki zainteresowania (wyświetlenia, zapisania) mierzone w czasie.

Pojedynczy odczyt mówi niewiele; liczy się przyrost. Każdy pomiar dopisujemy do
`detail["views_log"]` ([{"date", "views", "saved"}]), a `detail["stats"]` trzyma ostatni.

Rytm odświeżania zależy od wieku oferty: nowe (do NEW_DAYS dni) co NEW_EVERY dni, bo to one
najczęściej szybko znikają; starsze co OLD_EVERY dni. Liczbę zapytań w przebiegu ogranicza budżet.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from .http import FetchError

log = logging.getLogger(__name__)

NEW_DAYS = 14
NEVER_MEASURED = 10_000  # oferta bez pomiaru: najwyższy priorytet


def record(detail: dict, observed_at: date, views: int | None, saved: int | None = None) -> None:
    """Dopisuje pomiar (jeden na dzień). views=None: strona nie pokazała licznika."""
    day = observed_at.isoformat()
    entries = [e for e in detail.get("views_log") or [] if e.get("date") != day]
    if not entries and detail.get("stats", {}).get("views") is not None and detail["stats"].get("at") != day:
        # pomiar sprzed wprowadzenia dziennika (np. statystyki Otodom pobrane z historią)
        st = detail["stats"]
        entries.append({"date": st.get("at") or day, "views": st.get("views"), "saved": st.get("saved")})
    entries.append({"date": day, "views": views, "saved": saved})
    detail["views_log"] = sorted(entries, key=lambda e: e["date"])
    if views is not None:
        detail["stats"] = {"views": views, "saved": saved, "at": day}


def overdue(detail: dict, observed_at: date, listed_at: date | None, new_every: int, old_every: int) -> int:
    """Ile dni po terminie jest kolejny pomiar (>= 0: czas odświeżyć)."""
    entries = detail.get("views_log") or []
    if not entries:
        return NEVER_MEASURED
    first, last = date.fromisoformat(entries[0]["date"]), date.fromisoformat(entries[-1]["date"])
    start = min(first, listed_at) if listed_at else first
    every = new_every if (observed_at - start).days < NEW_DAYS else old_every
    return (observed_at - last).days - every


def refresh(items, cache, observed_at: date, budget: int, fetch: Callable, stats, label: str,
            new_every: int, old_every: int, url_of: Callable = lambda it: it.url) -> None:
    """Odświeża liczniki ofert, którym minął termin; najpierw najbardziej zaległe.

    `fetch(item, detail) -> (views, saved) | None`; FetchError = oferta niedostępna (pomijamy).
    """
    if budget <= 0:
        return
    due = []
    for it in items:
        detail = cache.get_detail(it.ad_id)
        if detail is None:
            continue
        od = overdue(detail, observed_at, getattr(it, "listed_at", None), new_every, old_every)
        if od >= 0:
            due.append((od, it, detail))
    due.sort(key=lambda x: -x[0])
    for _, it, detail in due[:budget]:
        try:
            result = fetch(it, detail)
        except FetchError as exc:
            stats.interest_failed += 1
            log.warning("%s: licznik %s: %s", label, it.ad_id, exc)
            continue
        if result is False:  # np. sesja wygasła: kończymy odświeżanie w tym przebiegu
            break
        views, saved = result if result else (None, None)
        record(detail, observed_at, views, saved)
        cache.put_detail(it.ad_id, url_of(it), detail)
        stats.interest_refreshed += 1
        if stats.interest_refreshed % 100 == 0:
            log.info("%s: odświeżono liczniki %d ofert", label, stats.interest_refreshed)
    stats.interest_due = len(due)
