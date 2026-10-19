-- Nowości dla zespołu (np. "działa filtr ofert od właścicieli"): widoczne na stronie do visible_until
-- (domyślnie 4 dni robocze od publikacji), dodaje i usuwa administrator.
CREATE TABLE IF NOT EXISTS app.announcements (
    announcement_id  serial PRIMARY KEY,
    title            text NOT NULL CHECK (length(title) BETWEEN 3 AND 140),
    body             text NOT NULL DEFAULT '' CHECK (length(body) <= 1500),
    created_by       text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    visible_until    date NOT NULL,
    removed_at       timestamptz
);
