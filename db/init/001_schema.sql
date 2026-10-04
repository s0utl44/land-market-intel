-- Land Market Intelligence — schemat bazy (PostgreSQL 16 + PostGIS)
--
-- core  : dane surowe, tylko dopisywanie (append-only). UPDATE/DELETE blokowane triggerem.
-- mart  : dane wyliczone (metryki), w całości odtwarzalne z core.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------------
-- Źródła danych. Import jest dozwolony tylko ze źródła z approved = true,
-- czyli takiego, dla którego sprawdzono regulamin / podstawę prawną.
-- Ta tabela jest jedyną w core, którą wolno aktualizować (zatwierdzenie źródła).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.sources (
    source_id       text PRIMARY KEY,
    name            text NOT NULL,
    approved        boolean NOT NULL DEFAULT false,
    legal_basis     text,           -- np. "umowa licencyjna z 2026-09-01", "dane publiczne RCN"
    approved_by     text,
    approved_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT approved OR (legal_basis IS NOT NULL AND approved_by IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS core.import_batches (
    batch_id        bigserial PRIMARY KEY,
    source_id       text NOT NULL REFERENCES core.sources(source_id),
    file_name       text NOT NULL,
    file_sha256     text NOT NULL UNIQUE,   -- ten sam plik nie wejdzie drugi raz
    rows_in_file    integer NOT NULL,
    rows_inserted   integer NOT NULL,
    rows_duplicate  integer NOT NULL,
    imported_at     timestamptz NOT NULL DEFAULT now()
);

-- Jedna obserwacja = jedno ogłoszenie widziane w danym dniu w danym źródle.
CREATE TABLE IF NOT EXISTS core.listing_observations (
    obs_id              bigserial PRIMARY KEY,
    batch_id            bigint NOT NULL REFERENCES core.import_batches(batch_id),
    source_id           text NOT NULL REFERENCES core.sources(source_id),
    source_listing_id   text NOT NULL,
    observed_at         date NOT NULL,
    municipality_teryt  text NOT NULL,
    municipality_name   text NOT NULL,
    parcel_id           text,
    lat                 double precision,
    lon                 double precision,
    geom                geography(Point, 4326)
                        GENERATED ALWAYS AS (
                            CASE WHEN lat IS NOT NULL AND lon IS NOT NULL
                                 THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography END
                        ) STORED,
    area_m2             numeric(12,2) NOT NULL CHECK (area_m2 > 0),
    price_pln           numeric(14,2) NOT NULL CHECK (price_pln > 0),
    land_use            text,
    url                 text,
    title               text,
    UNIQUE (source_id, source_listing_id, observed_at)
);

CREATE INDEX IF NOT EXISTS ix_obs_muni_date ON core.listing_observations (municipality_teryt, observed_at);
CREATE INDEX IF NOT EXISTS ix_obs_geom ON core.listing_observations USING gist (geom);

-- Wyniki deduplikacji: każde uruchomienie to nowy run, stare zostają (audyt).
CREATE TABLE IF NOT EXISTS core.dedup_runs (
    run_id              bigserial PRIMARY KEY,
    algorithm_version   text NOT NULL,
    params              jsonb NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.listing_property_links (
    run_id              bigint NOT NULL REFERENCES core.dedup_runs(run_id),
    source_id           text NOT NULL,
    source_listing_id   text NOT NULL,
    property_key        text NOT NULL,
    match_method        text NOT NULL,   -- single | parcel_id | location | price_area
    match_confidence    numeric(3,2) NOT NULL,
    PRIMARY KEY (run_id, source_id, source_listing_id)
);

-- ---------------------------------------------------------------------------
-- Append-only: blokada UPDATE / DELETE / TRUNCATE na tabelach core z danymi.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.forbid_modification() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Tabela %.% jest append-only (operacja % zabroniona)',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP;
END;
$$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['import_batches', 'listing_observations',
                             'dedup_runs', 'listing_property_links']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_no_update ON core.%I', t, t);
        EXECUTE format('CREATE TRIGGER trg_%s_no_update BEFORE UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.forbid_modification()', t, t);
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_no_truncate ON core.%I', t, t);
        EXECUTE format('CREATE TRIGGER trg_%s_no_truncate BEFORE TRUNCATE ON core.%I
                        FOR EACH STATEMENT EXECUTE FUNCTION core.forbid_modification()', t, t);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- mart: metryki tygodniowe per gmina (nadpisywane przy każdym przeliczeniu)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.weekly_region_metrics (
    municipality_teryt          text NOT NULL,
    municipality_name           text NOT NULL,
    week_start                  date NOT NULL,
    active_supply               integer NOT NULL,
    new_listings                integer NOT NULL,
    disappeared_listings        integer NOT NULL,
    median_price_per_m2         numeric(12,2),
    median_days_to_disappear    numeric(8,1),
    discounted_share            numeric(5,4),
    absorption_rate             numeric(6,4),
    dedup_run_id                bigint NOT NULL,
    computed_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (municipality_teryt, week_start)
);

CREATE TABLE IF NOT EXISTS mart.region_scores (
    municipality_teryt          text PRIMARY KEY,
    municipality_name           text NOT NULL,
    weeks_observed              integer NOT NULL,
    avg_absorption_rate         numeric(6,4),
    price_trend_pct             numeric(7,4),
    avg_discounted_share        numeric(5,4),
    median_days_to_disappear    numeric(8,1),
    opportunity_score           numeric(6,3),
    rank                        integer NOT NULL,
    dedup_run_id                bigint NOT NULL,
    computed_at                 timestamptz NOT NULL DEFAULT now()
);
