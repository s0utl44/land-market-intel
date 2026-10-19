"""Jednorazowe uzupełnienie parametrów ofert pobranych wcześniej (typ sprzedającego, media, archiwalne).

Codzienny przebieg uzupełnia stare oferty powoli (kilkaset dziennie). To polecenie robi to od razu dla
aktywnych ofert jednego portalu, w zwykłym, grzecznym tempie (PoliteClient), i można je przerwać w dowolnej
chwili: każda oferta zapisuje się od razu, a następne uruchomienie zaczyna od brakujących.
"""
from __future__ import annotations

import logging

from .scrapers import adresowo, gratka, nonline
from .scrapers.http import FetchError
from .scrapers.otodom import LayoutChanged
from .scrapers.pg_cache import PgCache

log = logging.getLogger(__name__)

PARSERS = {"gratka": gratka.parse_detail_page, "nieruchomosci-online": nonline.parse_detail_page,
           "adresowo": adresowo.parse_detail_page}
FEATURES_V = 2   # wersja odczytu parametrów; oferty z niższą wersją pobieramy ponownie


def pending(conn, source: str) -> list[tuple[str, str]]:
    """Aktywne oferty portalu (widziane w jego ostatnim pobraniu) bez aktualnych parametrów: [(ad_id, url)]."""
    return conn.execute(
        """SELECT o.source_listing_id, o.url
           FROM core.listing_observations o
           JOIN scrape.portal_details d ON d.source_id = o.source_id AND d.ad_id = o.source_listing_id
           WHERE o.source_id = %(s)s AND o.url IS NOT NULL
             AND o.observed_at = (SELECT max(observed_at) FROM core.listing_observations WHERE source_id = %(s)s)
             AND coalesce((d.detail->'features'->>'v')::int, 0) < %(v)s
             AND NOT EXISTS (SELECT 1 FROM scrape.excluded_listings x
                             WHERE x.source_id = o.source_id AND x.source_listing_id = o.source_listing_id)
           ORDER BY o.source_listing_id""", {"s": source, "v": FEATURES_V}).fetchall()


def run(conn, source: str, get, limit: int | None = None) -> dict:
    """Pobiera ponownie strony ofert z `pending` i zapisuje nowe parametry. Zwraca liczniki."""
    parse = PARSERS[source]
    cache = PgCache(conn, source)
    todo = pending(conn, source)[:limit] if limit else pending(conn, source)
    stats = {"pending": len(todo), "done": 0, "failed": 0, "archived": 0, "private": 0, "agency": 0}
    archived_ids = []
    for ad_id, url in todo:
        detail = cache.get_detail(ad_id) or {}
        try:
            fresh = parse(get(url), None, None)
        except (FetchError, LayoutChanged) as exc:
            stats["failed"] += 1
            log.info("%s: %s: %s", source, ad_id, exc)
            detail.setdefault("features", {})["v"] = FEATURES_V   # nie próbujemy w kółko
            cache.put_detail(ad_id, url, detail)
            continue
        f = dict(fresh.get("features") or {})
        f["v"] = FEATURES_V
        detail["features"] = f
        if fresh.get("archived"):
            detail["archived"] = True
            archived_ids.append(ad_id)
            stats["archived"] += 1
        cache.put_detail(ad_id, url, detail)
        stats["done"] += 1
        stats["private"] += f.get("seller") == "prywatny"
        stats["agency"] += f.get("seller") in ("biuro", "deweloper")
        if stats["done"] % 100 == 0:
            log.info("%s: uzupełniono %d z %d (prywatne %d, biura %d, archiwalne %d)", source, stats["done"],
                     len(todo), stats["private"], stats["agency"], stats["archived"])
    if archived_ids:
        from . import db
        db.exclude_listings(conn, source, archived_ids, "archiwalne")
    return stats
