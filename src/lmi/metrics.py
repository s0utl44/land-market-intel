"""Metryki tygodniowe per gmina, liczone w DuckDB na zdeduplikowanych nieruchomościach.

Wejście:
  observations — kolumny jak core.listing_observations (min. source_id, source_listing_id,
                 observed_at, municipality_teryt, municipality_name, area_m2, price_pln)
  links        — source_id, source_listing_id, property_key
Definicje: docs/metrics.md
"""
from __future__ import annotations

import duckdb
import pandas as pd

WEEKLY_SQL = """
WITH obs AS (
    SELECT o.*, l.property_key,
           CAST(date_trunc('week', o.observed_at) AS DATE) AS week_start
    FROM observations o
    JOIN links l USING (source_id, source_listing_id)
),
-- cena nieruchomości w tygodniu = mediana cen z wszystkich jej ogłoszeń w tym tygodniu
prop_week AS (
    SELECT property_key, week_start,
           any_value(municipality_teryt) AS municipality_teryt,
           any_value(municipality_name)  AS municipality_name,
           median(price_pln)             AS price_pln,
           median(price_pln / area_m2)   AS price_per_m2
    FROM obs
    GROUP BY property_key, week_start
),
prop AS (
    SELECT property_key,
           any_value(municipality_teryt) AS municipality_teryt,
           min(week_start)  AS first_week,
           max(week_start)  AS last_week,
           min(observed_at) AS first_seen,
           max(observed_at) AS last_seen,
           -- data wystawienia ze źródła (jeśli ją znamy) cofa początek oferty sprzed obserwacji
           least(min(observed_at), coalesce(min(listed_at), min(observed_at))) AS start_date,
           min(listed_at) IS NOT NULL AS start_known,
           arg_min(price_pln, observed_at) AS initial_price
    FROM obs
    GROUP BY property_key
),
bounds AS (
    SELECT min(week_start) AS min_week, max(week_start) AS max_week FROM obs
),
munis AS (
    SELECT municipality_teryt, any_value(municipality_name) AS municipality_name
    FROM obs GROUP BY municipality_teryt
),
grid AS (
    SELECT m.municipality_teryt, m.municipality_name, CAST(w.week_start AS DATE) AS week_start
    FROM munis m
    CROSS JOIN bounds b
    CROSS JOIN generate_series(b.min_week, b.max_week, INTERVAL 7 DAY) AS w(week_start)
),
-- nieruchomość jest aktywna od pierwszego do ostatniego tygodnia, w którym ją widziano
-- (luka w scrapowaniu nie powoduje "zniknięcia")
active AS (
    SELECT g.municipality_teryt, g.week_start, p.property_key, p.initial_price,
           CASE WHEN p.start_known OR p.first_week > (SELECT min_week FROM bounds)
                THEN greatest(date_diff('day', p.start_date, g.week_start), 0) END AS age_days
    FROM grid g
    JOIN prop p ON p.municipality_teryt = g.municipality_teryt
               AND g.week_start BETWEEN p.first_week AND p.last_week
),
-- ostatnia znana cena na dany tydzień
active_priced AS (
    SELECT a.*, pw.price_pln, pw.price_per_m2
    FROM active a
    ASOF JOIN prop_week pw
      ON a.property_key = pw.property_key AND a.week_start >= pw.week_start
),
supply AS (
    SELECT municipality_teryt, week_start,
           count(*)                                       AS active_supply,
           median(price_per_m2)                           AS median_price_per_m2,
           avg(CASE WHEN price_pln < initial_price * 0.99 THEN 1.0 ELSE 0.0 END) AS discounted_share,
           median(age_days) AS median_listing_age_days
    FROM active_priced
    GROUP BY municipality_teryt, week_start
),
new_l AS (
    SELECT municipality_teryt, first_week AS week_start, count(*) AS new_listings
    FROM prop GROUP BY 1, 2
),
-- zniknięcie liczymy w tygodniu PO ostatnim tygodniu widoczności (jeśli mieści się w danych)
gone AS (
    SELECT p.municipality_teryt,
           CAST(p.last_week + INTERVAL 7 DAY AS DATE) AS week_start,
           count(*) AS disappeared_listings,
           -- nieruchomości widoczne od pierwszego tygodnia danych są cenzurowane z lewej:
           -- bez daty wystawienia ze źródła nie znamy ich początku i nie wchodzą do mediany
           median(CASE WHEN p.start_known OR p.first_week > b.min_week
                       THEN date_diff('day', p.start_date, p.last_seen) END) AS median_days_to_disappear
    FROM prop p CROSS JOIN bounds b
    WHERE p.last_week < b.max_week
    GROUP BY 1, 2
)
SELECT g.municipality_teryt,
       g.municipality_name,
       g.week_start,
       coalesce(s.active_supply, 0)        AS active_supply,
       coalesce(n.new_listings, 0)         AS new_listings,
       coalesce(d.disappeared_listings, 0) AS disappeared_listings,
       round(s.median_price_per_m2, 2)     AS median_price_per_m2,
       round(d.median_days_to_disappear, 1) AS median_days_to_disappear,
       round(s.discounted_share, 4)        AS discounted_share,
       round(s.median_listing_age_days, 1) AS median_listing_age_days,
       round(coalesce(d.disappeared_listings, 0)
             / nullif(lag(s.active_supply) OVER (PARTITION BY g.municipality_teryt ORDER BY g.week_start), 0),
             4)                            AS absorption_rate
FROM grid g
LEFT JOIN supply s USING (municipality_teryt, week_start)
LEFT JOIN new_l  n USING (municipality_teryt, week_start)
LEFT JOIN gone   d USING (municipality_teryt, week_start)
ORDER BY g.municipality_teryt, g.week_start
"""

SCORES_SQL = """
WITH w AS (
    SELECT *, row_number() OVER (PARTITION BY municipality_teryt ORDER BY week_start) AS n,
              count(*)     OVER (PARTITION BY municipality_teryt)                     AS total
    FROM weekly
),
agg AS (
    SELECT municipality_teryt,
           any_value(municipality_name) AS municipality_name,
           count(*) AS weeks_observed,
           -- pierwszy tydzień pomijamy: cała podaż wygląda wtedy na "nową"
           avg(absorption_rate) FILTER (WHERE n > 1)             AS avg_absorption_rate,
           avg(median_price_per_m2) FILTER (WHERE n <= 4)        AS price_start,
           avg(median_price_per_m2) FILTER (WHERE n > total - 4) AS price_end,
           avg(discounted_share) FILTER (WHERE n > 1)            AS avg_discounted_share,
           median(median_days_to_disappear)                      AS median_days_to_disappear,
           avg(active_supply)                                    AS avg_active_supply,
           arg_max(active_supply, week_start)                    AS latest_active_supply,
           arg_max(median_price_per_m2, week_start)              AS latest_median_price_per_m2,
           arg_max(median_listing_age_days, week_start)          AS latest_median_listing_age_days
    FROM w GROUP BY municipality_teryt
),
feat AS (
    SELECT *, price_end / price_start - 1 AS price_trend_pct,
           avg_active_supply >= $min_supply AS rated
    FROM agg
),
-- średnie i odchylenia liczymy tylko z gmin ocenianych: gminy z kilkoma ofertami
-- mają przypadkowe wskaźniki i zaburzyłyby skalę
stats AS (
    SELECT avg(avg_absorption_rate) AS m_abs, stddev_pop(avg_absorption_rate) AS s_abs,
           avg(price_trend_pct) AS m_trend, stddev_pop(price_trend_pct) AS s_trend,
           avg(avg_discounted_share) AS m_disc, stddev_pop(avg_discounted_share) AS s_disc,
           avg(median_days_to_disappear) AS m_days, stddev_pop(median_days_to_disappear) AS s_days
    FROM feat WHERE rated
),
z AS (
    SELECT f.*,
        CASE WHEN rated THEN
            ( coalesce((avg_absorption_rate - m_abs) / nullif(s_abs, 0), 0)
            + coalesce((price_trend_pct - m_trend) / nullif(s_trend, 0), 0)
            - coalesce((avg_discounted_share - m_disc) / nullif(s_disc, 0), 0)
            - coalesce((median_days_to_disappear - m_days) / nullif(s_days, 0), 0)) / 4
        END AS score
    FROM feat f CROSS JOIN stats
)
SELECT municipality_teryt, municipality_name, weeks_observed,
       round(avg_absorption_rate, 4)  AS avg_absorption_rate,
       round(price_trend_pct, 4)      AS price_trend_pct,
       round(avg_discounted_share, 4) AS avg_discounted_share,
       round(median_days_to_disappear, 1) AS median_days_to_disappear,
       round(score, 3) AS opportunity_score,
       CAST(CASE WHEN rated THEN rank() OVER (ORDER BY score DESC NULLS LAST) END AS INTEGER) AS rank,
       round(avg_active_supply, 1)    AS avg_active_supply,
       CAST(latest_active_supply AS INTEGER) AS latest_active_supply,
       round(latest_median_price_per_m2, 2) AS latest_median_price_per_m2,
       round(latest_median_listing_age_days, 1) AS latest_median_listing_age_days
FROM z
ORDER BY rank NULLS LAST, latest_active_supply DESC
"""


def weekly_region_metrics(observations: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    obs = observations.copy()
    obs["observed_at"] = pd.to_datetime(obs["observed_at"]).dt.date
    obs["area_m2"] = obs["area_m2"].astype(float)
    obs["price_pln"] = obs["price_pln"].astype(float)
    if "listed_at" not in obs.columns:  # starsze dane / testy bez daty wystawienia
        obs["listed_at"] = None
    obs["listed_at"] = pd.to_datetime(obs["listed_at"]).dt.date
    con.register("observations", obs)
    con.register("links", links[["source_id", "source_listing_id", "property_key"]])
    return con.execute(WEEKLY_SQL).df()


MIN_SUPPLY_FOR_RANK = 10


def region_scores(weekly: pd.DataFrame, min_supply: float = MIN_SUPPLY_FOR_RANK) -> pd.DataFrame:
    """Ranking gmin. Wynik to średnia z-score'ów — ma sens tylko do porównania gmin
    w tym samym zbiorze danych, nie jako wartość bezwzględna.

    Gminy ze średnio mniej niż `min_supply` aktywnymi ofertami nie dostają oceny ani
    miejsca (NULL), ale zostają w tabeli z liczbą ofert i ceną."""
    con = duckdb.connect()
    con.register("weekly", weekly)
    return con.execute(SCORES_SQL, {"min_supply": min_supply}).df()
