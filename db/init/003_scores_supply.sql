-- Ranking: gminy z małą liczbą ofert nie dostają miejsca (rank NULL); dodatkowe kolumny podaży i ceny.
ALTER TABLE mart.region_scores ALTER COLUMN rank DROP NOT NULL;
ALTER TABLE mart.region_scores ADD COLUMN IF NOT EXISTS avg_active_supply numeric(10,1);
ALTER TABLE mart.region_scores ADD COLUMN IF NOT EXISTS latest_active_supply integer;
ALTER TABLE mart.region_scores ADD COLUMN IF NOT EXISTS latest_median_price_per_m2 numeric(12,2);
