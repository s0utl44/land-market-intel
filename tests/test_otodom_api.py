"""API konta Otodom: odpowiedzi w kształcie zarejestrowanym z serwera (2026-10)."""
import json
import urllib.parse
from datetime import date

import pytest

from lmi.scrapers import otodom
from lmi.scrapers.otodom_api import OtodomApi, SessionExpired, load_cookie, parse_history

from test_otodom import make_web


def money(v):
    return {"value": {"value": v, "currency": "PLN", "__typename": "Money"}, "type": "VISIBLE", "__typename": "AdvertPrice"}


HISTORY = {"data": {"advertHistory": {"__typename": "AdvertHistory", "entries": [
    {"changedAt": "2026-07-21T20:45:52+02:00", "status": "ACTIVE", "price": money(7000000.0), "imageCount": 3, "changeType": ["PRICE_UP"]},
    {"changedAt": "2013-05-08T00:16:02+00:00", "status": "ACTIVE", "price": None, "imageCount": None, "changeType": ["FIRST_PUBLISHED"]},
    {"changedAt": "2026-07-21T20:43:57+02:00", "status": "ACTIVE", "price": money(3500000.0), "imageCount": 3, "changeType": ["PRICE", "IMAGE"]},
    {"changedAt": "2026-09-13T20:00:30+02:00", "status": "ACTIVE", "price": money(5250000.0), "imageCount": 3, "changeType": ["PRICE_DOWN"]},
]}}}
STATS = {"data": {"adPageStatistics": {"__typename": "AdPageStatistics", "savedCount": 3, "viewsCount": 228}}}
FORBIDDEN = {"errors": [{"message": "Forbidden Access", "path": ["advertHistory"]}], "data": None}
PQNF = {"errors": [{"message": "PersistedQueryNotFound", "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"}}], "data": None}


class FakeApiWeb:
    def __init__(self, history=HISTORY, stats=STATS, forbidden_after=None, pqnf_once=False):
        self.history, self.stats, self.forbidden_after, self.pqnf_once = history, stats, forbidden_after, pqnf_once
        self.calls = []

    def get(self, url, headers=None):
        assert headers and "Cookie" in headers
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        op = q["operationName"][0]
        self.calls.append((op, json.loads(q["variables"][0])))
        if self.forbidden_after is not None and len(self.calls) > self.forbidden_after:
            return json.dumps(FORBIDDEN)
        if self.pqnf_once and len(self.calls) == 1:
            return json.dumps(PQNF)
        return json.dumps(self.history if op == "AdvertHistory" else self.stats)


def test_parse_history_sorted_and_simplified():
    h = parse_history(HISTORY)
    assert [e["date"] for e in h] == ["2013-05-08", "2026-07-21", "2026-07-21", "2026-09-13"]
    assert h[0] == {"date": "2013-05-08", "status": "ACTIVE", "price": None, "changes": ["FIRST_PUBLISHED"]}
    assert h[-1]["price"] == 5250000.0 and h[-1]["changes"] == ["PRICE_DOWN"]


def test_api_calls_and_statistics():
    web = FakeApiWeb()
    api = OtodomApi(web.get, "sesja=abc")
    assert len(api.history("18953365")) == 4
    assert api.statistics("18953365", "2013-05-08") == {"views": 228, "saved": 3}
    assert web.calls[0] == ("AdvertHistory", {"adID": "18953365"})
    assert web.calls[1] == ("AdPageStatistics", {"adID": "18953365", "from": "2013-05-08T00:00:00Z"})


def test_persisted_query_not_found_is_retried_once():
    web = FakeApiWeb(pqnf_once=True)
    assert len(OtodomApi(web.get, "c").history("1")) == 4
    assert len(web.calls) == 2


def test_forbidden_means_session_expired():
    api = OtodomApi(FakeApiWeb(forbidden_after=0).get, "stare")
    with pytest.raises(SessionExpired):
        api.history("1")
    assert api.alive is False


def test_load_cookie(tmp_path, monkeypatch):
    f = tmp_path / "c"
    f.write_text("a=1; b=2\n")
    assert load_cookie(str(f)) == "a=1; b=2"
    monkeypatch.setenv("LMI_OTODOM_COOKIE_FILE", str(tmp_path / "brak"))
    assert load_cookie() is None


def test_scrape_adds_history_for_new_ads_and_backfills_old():
    web, apiweb, cache = make_web(), FakeApiWeb(), otodom.MemoryCache()
    otodom.scrape(web.get, cache, date(2026, 10, 15))           # dzień bez konta: brak historii
    assert all("history" not in d for d in cache.details.values())

    api = OtodomApi(apiweb.get, "c")
    _, stats = otodom.scrape(web.get, cache, date(2026, 10, 16), api=api, history_backfill=2)
    assert stats.history_backfilled == 2 and stats.history_fetched == 0
    assert sum("history" in d for d in cache.details.values()) == 2
    d = next(d for d in cache.details.values() if "history" in d)
    assert d["stats"] == {"views": 228, "saved": 3, "at": "2026-10-16"}

    _, stats = otodom.scrape(web.get, cache, date(2026, 10, 17), api=api, history_backfill=100)
    assert stats.history_backfilled >= 1
    assert all("history" in d for d in cache.details.values() if d.get("lat") is not None and d["lat"] < 52)


def test_expired_session_does_not_stop_scraping():
    web = make_web()
    api = OtodomApi(FakeApiWeb(forbidden_after=0).get, "stare")
    rows, stats = otodom.scrape(web.get, otodom.MemoryCache(), date(2026, 10, 16), api=api)
    assert stats.session_expired and len(rows) == 3
    assert stats.history_fetched == 0
