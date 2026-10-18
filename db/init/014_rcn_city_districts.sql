-- Działki z delegatur Wrocławia (026402_9 … 026406_9) i dzielnic (rodzaj 8) przypisane do gminy miejskiej
-- ('0264011'), jak w ULDK i w ofertach. Wcześniej trafiały pod nieistniejące "gminy" 0264029 itd.
UPDATE scrape.rcn_parcels
   SET gmina_teryt = left(parcel_id, 4) || '011'
 WHERE substr(parcel_id, 7, 1) = '_' AND substr(parcel_id, 8, 1) IN ('8', '9')
   AND gmina_teryt IS DISTINCT FROM left(parcel_id, 4) || '011';
REFRESH MATERIALIZED VIEW mart.rcn_land_transactions;
