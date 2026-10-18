-- Ogłoszenia wyłączone z analizy (np. archiwalne na Nieruchomościach-online: lista portalu pokazuje je
-- za aktywnymi). Obserwacje zostają w core (tylko dopisywanie), ale deduplikacja i metryki ich nie biorą,
-- więc nie ma ich na stronie ani w licznikach "wycofanych".
CREATE TABLE IF NOT EXISTS scrape.excluded_listings (
    source_id          text NOT NULL,
    source_listing_id  text NOT NULL,
    reason             text NOT NULL,
    added_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, source_listing_id)
);
