-- Archiwum: dawne zgłoszenia ze strony Radaru (do 25.10.2026). Nowe zgłoszenia są wspólne dla całej witryny
-- (pasek „Zgłoś błąd”, panel Administracja w Kartotece) – tabela zostaje tylko z historią.
CREATE TABLE IF NOT EXISTS app.feedback (
    feedback_id     bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    user_email      text NOT NULL,           -- login z bramki albo e-mail z logowania Google
    kind            text NOT NULL CHECK (kind IN ('błąd', 'poprawka danych', 'pomysł')),
    body            text NOT NULL CHECK (length(body) BETWEEN 3 AND 4000),
    context         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- gdzie na stronie: gmina, widok, przeglądarka
    status          text NOT NULL DEFAULT 'nowe' CHECK (status IN ('nowe', 'zrobione')),
    resolved_at     timestamptz
);
CREATE INDEX IF NOT EXISTS feedback_status ON app.feedback (status, created_at);
