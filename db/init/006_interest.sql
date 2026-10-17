-- Tempo zainteresowania ofertą: wyświetlenia na dzień.
-- Z dwóch i więcej pomiarów (scrape.*.detail->'views_log'): przyrost / liczba dni między pierwszym a ostatnim.
-- Z jednego pomiaru: wyświetlenia / dni od wystawienia oferty (średnia od początku).
CREATE OR REPLACE FUNCTION scrape.views_per_day(log jsonb, start_date date)
RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    WITH e AS (
        SELECT (x->>'date')::date AS d, (x->>'views')::numeric AS v
        FROM jsonb_array_elements(CASE WHEN jsonb_typeof(log) = 'array' THEN log ELSE '[]'::jsonb END) x
        WHERE x->>'views' IS NOT NULL
    ),
    f AS (SELECT d, v FROM e ORDER BY d LIMIT 1),
    l AS (SELECT d, v FROM e ORDER BY d DESC LIMIT 1)
    SELECT CASE
        WHEN l.d > f.d THEN round(greatest(l.v - f.v, 0) / (l.d - f.d), 1)
        WHEN start_date IS NOT NULL THEN round(l.v / greatest(l.d - start_date, 1), 1)
    END
    FROM f, l
$$;
