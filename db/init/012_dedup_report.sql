-- Kontrola jakości deduplikacji (podejrzane grupy, prawie-duplikaty, nieprawdopodobne ceny) przy każdym runie.
ALTER TABLE core.dedup_runs ADD COLUMN IF NOT EXISTS report jsonb;
