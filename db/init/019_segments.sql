-- Metryki i podsumowania osobno dla typów działek (segment): 'wszystkie', 'budowlana', 'rolna', ...
-- Strona domyślnie pokazuje budowlane.
ALTER TABLE mart.weekly_region_metrics ADD COLUMN IF NOT EXISTS segment text NOT NULL DEFAULT 'wszystkie';
ALTER TABLE mart.region_scores ADD COLUMN IF NOT EXISTS segment text NOT NULL DEFAULT 'wszystkie';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'weekly_region_metrics_pkey'
               AND array_length(conkey, 1) = 2) THEN
        ALTER TABLE mart.weekly_region_metrics DROP CONSTRAINT weekly_region_metrics_pkey;
        ALTER TABLE mart.weekly_region_metrics ADD PRIMARY KEY (segment, municipality_teryt, week_start);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'region_scores_pkey'
               AND array_length(conkey, 1) = 1) THEN
        ALTER TABLE mart.region_scores DROP CONSTRAINT region_scores_pkey;
        ALTER TABLE mart.region_scores ADD PRIMARY KEY (segment, municipality_teryt);
    END IF;
END $$;

-- gotowe "Co się zmieniło" per okres i typ działek (zastępuje mart.changes_snapshot)
DROP TABLE IF EXISTS mart.changes_snapshot;
CREATE TABLE IF NOT EXISTS mart.changes_cache (
    days         integer NOT NULL,
    segment      text NOT NULL,
    state        text NOT NULL,
    data         jsonb NOT NULL,
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (days, segment)
);
