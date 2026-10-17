-- Stan zadań na bieżąco (pobieranie portali, RCN): co trwa, ostatni komunikat, jak się skończyło.
-- Aktualizowane przez same zadania (lmi.jobs), czytane przez stronę (panel "Status" administratora).
CREATE TABLE IF NOT EXISTS scrape.job_status (
    job             text PRIMARY KEY,        -- otodom / gratka / nieruchomosci-online / adresowo / rcn
    state           text NOT NULL,           -- running / ok / warning / error / blocked / layout_changed
    started_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    message         text
);
