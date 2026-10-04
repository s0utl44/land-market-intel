"""Metryki sprawdzane na ręcznie policzonym przykładzie (wartości oczekiwane w komentarzach)."""
from datetime import date

import pandas as pd
import pytest

from lmi import dedup, metrics

W0, W1, W2, W3 = date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16), date(2026, 3, 23)


def obs(src, lid, d, price, area=1000.0, muni="1465011"):
    return {"source_id": src, "source_listing_id": lid, "observed_at": d, "municipality_teryt": muni,
            "municipality_name": "Testowa", "area_m2": area, "price_pln": price}


@pytest.fixture
def weekly():
    rows = [
        # P1: dwa portale (duplikat b/9), widoczna W0-W1
        obs("a", "1", W0, 100_000), obs("a", "1", W1, 100_000), obs("b", "9", W0, 100_000),
        # P2: cała seria, obniżka 200k -> 180k od W2
        obs("a", "2", W0, 200_000), obs("a", "2", W1, 200_000),
        obs("a", "2", W2, 180_000), obs("a", "2", W3, 180_000),
        # P3: W1-W2, oglądana we wtorki
        obs("a", "3", date(2026, 3, 10), 50_000, 500), obs("a", "3", date(2026, 3, 17), 50_000, 500),
        # P4: tylko W3
        obs("a", "4", W3, 300_000),
    ]
    links = pd.DataFrame([
        {"source_id": "a", "source_listing_id": "1", "property_key": "P1"},
        {"source_id": "b", "source_listing_id": "9", "property_key": "P1"},
        {"source_id": "a", "source_listing_id": "2", "property_key": "P2"},
        {"source_id": "a", "source_listing_id": "3", "property_key": "P3"},
        {"source_id": "a", "source_listing_id": "4", "property_key": "P4"},
    ])
    return metrics.weekly_region_metrics(pd.DataFrame(rows), links).set_index("week_start")



def test_active_supply_counts_properties_not_listings(weekly):
    assert list(weekly["active_supply"]) == [2, 3, 2, 2]


def test_new_and_disappeared(weekly):
    assert list(weekly["new_listings"]) == [2, 1, 0, 1]
    # P1 znika w W2, P3 w W3; P2 i P4 są w ostatnim tygodniu danych -> nie znikają
    assert list(weekly["disappeared_listings"]) == [0, 0, 1, 1]


def test_median_price_per_m2(weekly):
    # W0: 100,200 | W1: 100,200,100 | W2: 180,100 | W3: 180,300
    assert list(weekly["median_price_per_m2"]) == [150, 100, 140, 240]


def test_discounted_share(weekly):
    assert list(weekly["discounted_share"]) == [0, 0, 0.5, 0.5]


def test_absorption_rate(weekly):
    # zniknięte / podaż z poprzedniego tygodnia
    assert pd.isna(weekly["absorption_rate"].iloc[0])
    assert list(weekly["absorption_rate"].iloc[1:]) == [0, round(1 / 3, 4), 0.5]


def test_days_to_disappear_excludes_left_censored(weekly):
    # P1 była od pierwszego tygodnia danych -> pomijana; P3: 10.03 -> 17.03 = 7 dni
    assert pd.isna(weekly["median_days_to_disappear"].iloc[2])
    assert weekly["median_days_to_disappear"].iloc[3] == 7


def test_gap_in_observations_does_not_count_as_disappearance():
    rows = [obs("a", "1", W0, 1e5), obs("a", "1", W2, 1e5), obs("a", "2", W0, 1e5), obs("a", "2", W2, 1e5)]
    links = pd.DataFrame([{"source_id": "a", "source_listing_id": i, "property_key": f"P{i}"} for i in "12"])
    w = metrics.weekly_region_metrics(pd.DataFrame(rows), links)
    assert list(w["active_supply"]) == [2, 2, 2]
    assert list(w["disappeared_listings"]) == [0, 0, 0]


def test_region_without_activity_in_a_week_gets_zero_supply():
    rows = [obs("a", "1", W0, 1e5), obs("a", "2", W2, 1e5, muni="1465028")]
    links = pd.DataFrame([{"source_id": "a", "source_listing_id": i, "property_key": f"P{i}"} for i in "12"])
    w = metrics.weekly_region_metrics(pd.DataFrame(rows), links)
    second = w[w.municipality_teryt == "1465028"]
    assert list(second["active_supply"]) == [0, 0, 1]


def test_region_scores_rank_synthetic_regions(synthetic_data):
    rows = synthetic_data["rows"]
    links = dedup.deduplicate(dedup.listings_from_observations(rows))
    weekly = metrics.weekly_region_metrics(pd.DataFrame(rows), pd.DataFrame([l.__dict__ for l in links]))
    scores = metrics.region_scores(weekly)
    assert list(scores["municipality_name"]) == [
        "Syntetyczna Rozwojowa", "Syntetyczna Stabilna", "Syntetyczna Zastój"]
    assert scores["opportunity_score"].sum() == pytest.approx(0, abs=0.01)  # średnia z-score'ów
    rozw = scores.iloc[0]
    assert rozw.avg_absorption_rate > 0.07 and rozw.avg_discounted_share < 0.1
