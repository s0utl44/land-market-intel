-- Stan scraperów (cache). To NIE są dane źródłowe — wolno je nadpisywać i czyścić.

CREATE SCHEMA IF NOT EXISTS scrape;

-- Szczegóły ogłoszenia Otodom pobierane raz (współrzędne, typ działki).
CREATE TABLE IF NOT EXISTS scrape.otodom_details (
    ad_id           text PRIMARY KEY,
    slug            text NOT NULL,
    detail          jsonb NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now()
);

-- Gmina dla punktu (klucz: współrzędne zaokrąglone do 4 miejsc, ~10 m).
CREATE TABLE IF NOT EXISTS scrape.uldk_communes (
    coord_key       text PRIMARY KEY,
    teryt           text NOT NULL,
    name            text,
    fetched_at      timestamptz NOT NULL DEFAULT now()
);

-- Dziennik przebiegów: do wykrywania awarii (np. nagły spadek liczby ogłoszeń).
CREATE TABLE IF NOT EXISTS scrape.runs (
    run_id          bigserial PRIMARY KEY,
    source_id       text NOT NULL,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz NOT NULL DEFAULT now(),
    status          text NOT NULL,          -- ok | warning | blocked | layout_changed | error
    rows_written    integer,
    stats           jsonb,
    message         text
);
