-- Pozwolenia na budowę z rejestru GUNB (RWDZ), bez danych osobowych (inwestor, adres, projektant).
-- Jeden wiersz = działka we wniosku/decyzji; pozwolenie = numer_gunb.
CREATE TABLE IF NOT EXISTS scrape.gunb_permits (
    numer_gunb   text NOT NULL,
    parcel       text NOT NULL,          -- jednostka|obręb|działka
    gmina_teryt  text NOT NULL,
    filed_on     date,                   -- wpływ wniosku
    decided_on   date,                   -- wydanie decyzji
    kind         text,                   -- rodzaj inwestycji, np. "Budynek mieszkalny jednorodzinny"
    category     text,                   -- kategoria obiektu (I = domy jednorodzinne)
    volume       numeric,                -- kubatura
    PRIMARY KEY (numer_gunb, parcel)
);
CREATE INDEX IF NOT EXISTS ix_gunb_gmina ON scrape.gunb_permits (gmina_teryt, decided_on);

CREATE TABLE IF NOT EXISTS scrape.gunb_fetch_log (
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    rows        integer NOT NULL,
    permits     integer NOT NULL
);

-- Pozwolenia (decyzje) per gmina: jedno pozwolenie raz, gmina z pierwszej działki.
-- Strona czyta zmaterializowaną kopię (mart.gunb_permits), odświeżaną po wczytaniu pliku (lmi.gunb.load).
CREATE OR REPLACE VIEW mart.gunb_permits_live AS
SELECT numer_gunb, min(gmina_teryt) AS gmina_teryt, min(filed_on) AS filed_on, min(decided_on) AS decided_on,
       min(kind) AS kind, min(category) AS category, max(volume) AS volume, count(*) AS parcels,
       bool_or(kind ILIKE 'Budynek mieszkalny jednorodzinny%' OR category = 'I') AS single_family
FROM scrape.gunb_permits
GROUP BY numer_gunb;

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.gunb_permits AS SELECT * FROM mart.gunb_permits_live;
CREATE UNIQUE INDEX IF NOT EXISTS ux_gunb_permits ON mart.gunb_permits (numer_gunb);
CREATE INDEX IF NOT EXISTS ix_gunb_permits_gmina ON mart.gunb_permits (gmina_teryt, decided_on);
