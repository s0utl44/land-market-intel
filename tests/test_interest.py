from datetime import date

from lmi.scrapers import interest, otodom
from lmi.scrapers.http import FetchError


class Item:
    def __init__(self, ad_id, listed_at=None):
        self.ad_id, self.url, self.listed_at = ad_id, f"https://x/{ad_id}", listed_at


class Stats:
    interest_refreshed = interest_failed = interest_due = 0


def test_record_keeps_one_entry_per_day_and_seeds_old_stats():
    d = {"stats": {"views": 10, "saved": 1, "at": "2026-10-01"}}
    interest.record(d, date(2026, 10, 5), 30, 2)
    interest.record(d, date(2026, 10, 5), 31, 2)
    assert d["views_log"] == [{"date": "2026-10-01", "views": 10, "saved": 1},
                              {"date": "2026-10-05", "views": 31, "saved": 2}]
    assert d["stats"] == {"views": 31, "saved": 2, "at": "2026-10-05"}
    interest.record(d, date(2026, 10, 6), None)  # licznik zniknął ze strony: stats bez zmian
    assert d["stats"]["views"] == 31 and d["views_log"][-1]["views"] is None


def test_overdue_depends_on_offer_age():
    new = {"views_log": [{"date": "2026-10-10", "views": 5}]}
    assert interest.overdue(new, date(2026, 10, 12), date(2026, 10, 9), 2, 7) == 0     # nowa: co 2 dni
    old = {"views_log": [{"date": "2026-10-10", "views": 5}]}
    assert interest.overdue(old, date(2026, 10, 12), date(2026, 8, 1), 2, 7) == -5     # stara: co 7 dni
    assert interest.overdue({}, date(2026, 10, 12), None, 2, 7) == interest.NEVER_MEASURED


def test_refresh_respects_budget_and_priority():
    cache = otodom.MemoryCache()
    today = date(2026, 10, 20)
    cache.put_detail("never", "u", {})
    cache.put_detail("late", "u", {"views_log": [{"date": "2026-10-01", "views": 1}]})
    cache.put_detail("fresh", "u", {"views_log": [{"date": "2026-10-19", "views": 1}]})
    cache.put_detail("gone", "u", {"views_log": [{"date": "2026-10-02", "views": 1}]})
    calls = []

    def fetch(it, detail):
        calls.append(it.ad_id)
        if it.ad_id == "gone":
            raise FetchError("404")
        return 50, None

    items = [Item("fresh", date(2026, 10, 18)), Item("late", date(2026, 9, 1)), Item("never"), Item("gone")]
    st = Stats()
    interest.refresh(items, cache, today, 2, fetch, st, "t", 2, 7)
    assert calls == ["never", "late"]  # najbardziej zaległe najpierw, budżet 2
    assert "fresh" not in calls and st.interest_due == 3
    assert cache.get_detail("never")["stats"]["views"] == 50
