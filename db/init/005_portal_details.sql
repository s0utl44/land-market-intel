-- Cache szczegółów ofert dla portali innych niż Otodom (Otodom ma własną tabelę otodom_details).
CREATE TABLE IF NOT EXISTS scrape.portal_details (
    source_id       text NOT NULL,
    ad_id           text NOT NULL,
    url             text NOT NULL,
    detail          jsonb NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, ad_id)
);
