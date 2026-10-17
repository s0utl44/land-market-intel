-- Praca zespołu na ofertach: ulubione (każdy swoje) i komentarze (widoczne dla zespołu).
-- Przypięte do ogłoszenia z portalu (source_id, source_listing_id), a nie do property_key,
-- bo property_key zmienia się przy każdej deduplikacji. Działka = wszystkie jej ogłoszenia.
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.favorites (
    user_email          text NOT NULL,
    source_id           text NOT NULL,
    source_listing_id   text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_email, source_id, source_listing_id)
);

CREATE TABLE IF NOT EXISTS app.comments (
    comment_id          bigserial PRIMARY KEY,
    source_id           text NOT NULL,
    source_listing_id   text NOT NULL,
    user_email          text NOT NULL,
    body                text NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    created_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz
);
CREATE INDEX IF NOT EXISTS comments_listing ON app.comments (source_id, source_listing_id);
