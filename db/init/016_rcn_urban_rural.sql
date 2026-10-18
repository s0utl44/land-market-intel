-- Gminy miejsko-wiejskie: działki z jednostek ewidencyjnych miasta (_4) i obszaru wiejskiego (_5) należą
-- do gminy (rodzaj 3), jak w ULDK i w ofertach. Wcześniej trafiały pod kody 0223044 / 0223045 zamiast 0223043.
UPDATE scrape.rcn_parcels
   SET gmina_teryt = left(parcel_id, 6) || '3'
 WHERE substr(parcel_id, 7, 1) = '_' AND substr(parcel_id, 8, 1) IN ('4', '5')
   AND gmina_teryt IS DISTINCT FROM left(parcel_id, 6) || '3';
REFRESH MATERIALIZED VIEW mart.rcn_land_transactions;
