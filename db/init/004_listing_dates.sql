-- Daty z ogłoszenia: pierwsze dodanie w źródle i ostatnie płatne podbicie.
-- Starsze obserwacje mają NULL (pola zbieramy od 2026-10-16).
ALTER TABLE core.listing_observations ADD COLUMN IF NOT EXISTS listed_at date;
ALTER TABLE core.listing_observations ADD COLUMN IF NOT EXISTS pushed_up_at date;
ALTER TABLE mart.weekly_region_metrics ADD COLUMN IF NOT EXISTS median_listing_age_days numeric(8,1);
ALTER TABLE mart.region_scores ADD COLUMN IF NOT EXISTS latest_median_listing_age_days numeric(8,1);
