-- RCN tylko od 2024 roku: niepełne pobranie z 2020 (z lukami geoportalu) usuwamy raz, żeby nie mieszało się
-- w wykresach i statystykach. To dane publiczne — w razie potrzeby można je pobrać ponownie (lmi rcn --since).
CREATE TABLE IF NOT EXISTS scrape.one_off (
    name     text PRIMARY KEY,
    done_at  timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM scrape.one_off WHERE name = 'rcn_since_2024') THEN
        DELETE FROM scrape.rcn_parcels WHERE doc_date < DATE '2024-01-01';
        DELETE FROM scrape.rcn_fetch_log WHERE period_start < DATE '2024-01-01';
        INSERT INTO scrape.one_off (name) VALUES ('rcn_since_2024');
    END IF;
END $$;
