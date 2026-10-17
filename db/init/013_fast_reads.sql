-- Szybki odczyt strony: wyniki liczone raz po pobraniu danych, nie przy każdym wejściu.

-- 1. Transakcje gruntowe RCN: zmaterializowane (ok. 190 tys. rekordów działek -> ok. 20 tys. transakcji),
--    odświeżane po każdym pobraniu RCN (lmi.rcn.refresh_land).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'mart' AND c.relname = 'rcn_land_transactions' AND c.relkind = 'v') THEN
        DROP VIEW mart.rcn_land_transactions;
    END IF;
END $$;
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.rcn_land_transactions AS
    SELECT * FROM mart.rcn_land_transactions_live;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rcn_land_tx ON mart.rcn_land_transactions (tx_id);
CREATE INDEX IF NOT EXISTS ix_rcn_land_gmina ON mart.rcn_land_transactions (gmina_teryt, doc_date);

-- 2. "Co się zmieniło": gotowe odpowiedzi dla okresów 1 / 7 / 30 dni, przeliczane po pobraniu i deduplikacji.
CREATE TABLE IF NOT EXISTS mart.changes_snapshot (
    days         integer PRIMARY KEY,
    state        text NOT NULL,            -- stan danych, z którego liczono (ostatni dzień, dedup, RCN)
    data         jsonb NOT NULL,
    computed_at  timestamptz NOT NULL DEFAULT now()
);
