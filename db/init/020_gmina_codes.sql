-- Stare kody gmin w rejestrach (GUNB, RCN): gmina zmieniła rodzaj (np. Miękinia 0218032 -> 0218033 po nadaniu
-- praw miejskich), a jednostki ewidencyjne i adresy zostały ze starym kodem. Kod, którego nie ma wśród aktualnych
-- gmin (z ofert/ULDK), przypinamy do jedynej aktualnej gminy z tym samym numerem (pierwsze 6 cyfr).
CREATE OR REPLACE FUNCTION scrape.fix_gmina_codes() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n integer := 0; k integer;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS tmp_gmina_alias (old text PRIMARY KEY, new text NOT NULL) ON COMMIT DROP;
    DELETE FROM tmp_gmina_alias;
    INSERT INTO tmp_gmina_alias
    WITH cur AS (SELECT DISTINCT teryt AS t FROM scrape.uldk_communes WHERE teryt ~ '^\d{7}$'
                 UNION SELECT municipality_teryt FROM mart.region_scores),
         one AS (SELECT left(t, 6) AS p, min(t) AS t FROM cur GROUP BY 1 HAVING count(*) = 1),
         used AS (SELECT DISTINCT gmina_teryt AS c FROM scrape.gunb_permits
                  UNION SELECT DISTINCT gmina_teryt FROM scrape.rcn_parcels)
    SELECT u.c, one.t FROM used u JOIN one ON one.p = left(u.c, 6)
    WHERE u.c IS NOT NULL AND u.c NOT IN (SELECT t FROM cur);
    UPDATE scrape.gunb_permits g SET gmina_teryt = a.new FROM tmp_gmina_alias a WHERE g.gmina_teryt = a.old;
    GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
    UPDATE scrape.rcn_parcels r SET gmina_teryt = a.new FROM tmp_gmina_alias a WHERE r.gmina_teryt = a.old;
    GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
    DROP TABLE tmp_gmina_alias;
    RETURN n;
END $$;

DO $$
BEGIN
    IF scrape.fix_gmina_codes() > 0 THEN
        REFRESH MATERIALIZED VIEW mart.gunb_permits;
        REFRESH MATERIALIZED VIEW mart.rcn_land_transactions;
    END IF;
END $$;
