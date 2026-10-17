-- Ceny transakcyjne z Rejestru Cen Nieruchomości (RCN, geoportal GUGiK, dane bezpłatne).
-- Jeden wiersz = działka w transakcji (akcie). Bez nazwisk notariuszy i pełnych adresów.
CREATE TABLE IF NOT EXISTS scrape.rcn_parcels (
    tx_id           text NOT NULL,           -- TRAN_LOKALNY_ID_IIP
    parcel_id       text NOT NULL,           -- DZI_ID_DZIALKI, np. 022302_2.0012.401/2
    gmina_teryt     text,                    -- 7 cyfr, jak w ULDK i w ogłoszeniach
    doc_date        date,                    -- data aktu
    tran_type       text,                    -- wolnyRynek / sprzedazPrzetargowa / sprzedazZBonifikata ...
    market          text,                    -- rynekPierwotny / rynekWtorny
    seller_type     text,                    -- osobaFizyczna / osobaPrawna ...
    buyer_type      text,
    tran_price      numeric,                 -- cena całej transakcji brutto
    nier_type       text NOT NULL DEFAULT '', -- nieruchomoscGruntowaNiezabudowana / ...Zabudowana / ...Lokalowa
    nier_right      text,
    share           text NOT NULL DEFAULT '', -- udział, np. 1/1 ('' = nie podano)
    nier_price      numeric,
    mpzp            text,                    -- przeznaczenie w planie miejscowym
    area_m2         numeric,                 -- powierzchnia ewidencyjna działki
    land_use        text,                    -- sposób użytkowania z ewidencji
    parcel_price    numeric,
    locality        text,                    -- miejscowość (bez ulicy)
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tx_id, parcel_id, nier_type, share)
);
CREATE INDEX IF NOT EXISTS rcn_parcels_gmina_date ON scrape.rcn_parcels (gmina_teryt, doc_date);

-- Dziennik pobrań: ile rekordów usługa zadeklarowała w okresie i ile zapisaliśmy (kontrola kompletności).
CREATE TABLE IF NOT EXISTS scrape.rcn_fetch_log (
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    teryt_prefix    text NOT NULL,
    period_start    date,                    -- NULL = akty bez daty
    period_end      date,
    matched         integer NOT NULL,
    saved           integer NOT NULL
);

-- Transakcje samym gruntem: każda działka niezabudowana, w całości, wolny rynek albo przetarg,
-- jedna gmina. Mieszane (dom + działka, lokal z udziałem w gruncie, bonifikaty) pomijamy.
CREATE OR REPLACE VIEW mart.rcn_land_transactions AS
SELECT tx_id,
       min(gmina_teryt)                                       AS gmina_teryt,
       min(doc_date)                                          AS doc_date,
       max(tran_price)                                        AS price,
       sum(area_m2)                                           AS area_m2,
       round(max(tran_price) / nullif(sum(area_m2), 0), 2)    AS ppm2,
       count(*)                                               AS parcels,
       string_agg(DISTINCT mpzp, ';')                         AS mpzp,
       string_agg(DISTINCT land_use, ';')                     AS land_use,
       bool_or(tran_type = 'sprzedazPrzetargowa')             AS tender,
       min(market)                                            AS market,
       min(seller_type)                                       AS seller_type,
       min(buyer_type)                                        AS buyer_type,
       min(locality)                                          AS locality,
       array_agg(parcel_id ORDER BY parcel_id)                AS parcel_ids,
       -- działka pod zabudowę: plan miejscowy przewiduje zabudowę albo ewidencja mówi "zabudowane"
       bool_or(mpzp ILIKE '%budownictwo%' OR mpzp ILIKE '%uslug%' OR mpzp ILIKE '%zabudow%'
               OR land_use = 'gruntyZabudowaneIZurbanizowane')  AS buildable
FROM scrape.rcn_parcels
GROUP BY tx_id
HAVING bool_and(nier_type = 'nieruchomoscGruntowaNiezabudowana')
   AND bool_and(share IN ('1/1', ''))
   AND bool_and(tran_type IN ('wolnyRynek', 'sprzedazPrzetargowa'))
   AND count(DISTINCT gmina_teryt) = 1
   AND max(tran_price) >= 1000
   AND sum(area_m2) > 0;
