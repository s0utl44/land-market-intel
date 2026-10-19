"""Operacje na PostgreSQL: rejestracja źródeł, import CSV, zapis deduplikacji i metryk."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import psycopg

from . import csv_import, dedup, metrics

DEFAULT_DSN = "postgresql://lmi:lmi@localhost:5432/lmi"
# W repo: <repo>/db/init. W obrazie Dockera: LMI_SCHEMA_DIR=/app/db/init.
SCHEMA_DIR = Path(os.environ.get("LMI_SCHEMA_DIR", Path(__file__).resolve().parents[2] / "db" / "init"))


def connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or os.environ.get("LMI_DATABASE_URL", DEFAULT_DSN))


def apply_schema(conn: psycopg.Connection, schema_dir: Path = SCHEMA_DIR) -> None:
    files = sorted(Path(schema_dir).glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"Brak plików schematu w {schema_dir} (ustaw LMI_SCHEMA_DIR)")
    for path in files:
        conn.execute(path.read_text(encoding="utf-8"))
    conn.commit()


@contextmanager
def _committed(conn):
    """Transakcja zatwierdzana na końcu bloku.

    Samo conn.transaction() wewnątrz już otwartej (niejawnej) transakcji tworzy tylko
    savepoint — zmiany przepadłyby przy późniejszym rollbacku.
    """
    with conn.transaction():
        yield
    conn.commit()


class ImportRejected(Exception):
    pass


def add_source(conn, source_id: str, name: str) -> None:
    conn.execute(
        "INSERT INTO core.sources (source_id, name) VALUES (%s, %s) ON CONFLICT (source_id) DO NOTHING",
        (source_id, name),
    )
    conn.commit()


def approve_source(conn, source_id: str, legal_basis: str, approved_by: str) -> None:
    cur = conn.execute(
        """UPDATE core.sources SET approved = true, legal_basis = %s, approved_by = %s, approved_at = now()
           WHERE source_id = %s""",
        (legal_basis, approved_by, source_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ImportRejected(f"Nieznane źródło: {source_id}")
    conn.commit()


@dataclass
class ImportResult:
    batch_id: int
    rows_in_file: int
    rows_inserted: int
    rows_duplicate: int


def import_csv(conn, source_id: str, path: str | Path, allow_partial: bool = False) -> ImportResult:
    row = conn.execute("SELECT approved FROM core.sources WHERE source_id = %s", (source_id,)).fetchone()
    if row is None:
        raise ImportRejected(f"Źródło {source_id!r} nie jest zarejestrowane (lmi add-source)")
    if not row[0]:
        raise ImportRejected(
            f"Źródło {source_id!r} nie jest zatwierdzone. Najpierw sprawdź podstawę prawną "
            f"(docs/legal_checklist.md) i uruchom lmi approve-source."
        )

    path = Path(path)
    parsed = csv_import.parse_file(path)
    if parsed.errors and not allow_partial:
        shown = "\n  ".join(parsed.errors[:20])
        more = f"\n  ... i {len(parsed.errors) - 20} więcej" if len(parsed.errors) > 20 else ""
        raise ImportRejected(f"Plik ma {len(parsed.errors)} błędnych wierszy:\n  {shown}{more}")

    exists = conn.execute(
        "SELECT batch_id FROM core.import_batches WHERE file_sha256 = %s", (parsed.sha256,)
    ).fetchone()
    if exists:
        raise ImportRejected(f"Ten plik był już zaimportowany (batch {exists[0]})")

    with _committed(conn):
        # import_batches jest append-only, więc liczniki muszą być znane przed INSERT:
        # najpierw liczymy wiersze, które już są w bazie
        keys = [(o.source_listing_id, o.observed_at) for o in parsed.observations]
        dup = 0
        if keys:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT count(*) FROM core.listing_observations o
                       JOIN unnest(%s::text[], %s::date[]) AS k(lid, d)
                         ON o.source_listing_id = k.lid AND o.observed_at = k.d
                       WHERE o.source_id = %s""",
                    ([k[0] for k in keys], [k[1] for k in keys], source_id),
                )
                dup = cur.fetchone()[0]
        batch_id = conn.execute(
            """INSERT INTO core.import_batches
                   (source_id, file_name, file_sha256, rows_in_file, rows_inserted, rows_duplicate)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING batch_id""",
            (source_id, path.name, parsed.sha256, parsed.rows_in_file,
             len(parsed.observations) - dup, dup),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO core.listing_observations
                       (batch_id, source_id, source_listing_id, observed_at, municipality_teryt,
                        municipality_name, parcel_id, lat, lon, area_m2, price_pln, land_use, url, title,
                        listed_at, pushed_up_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (source_id, source_listing_id, observed_at) DO NOTHING""",
                [
                    (batch_id, source_id, o.source_listing_id, o.observed_at, o.municipality_teryt,
                     o.municipality_name, o.parcel_id, o.lat, o.lon, o.area_m2, o.price_pln,
                     o.land_use, o.url, o.title, o.listed_at, o.pushed_up_at)
                    for o in parsed.observations
                ],
            )
    return ImportResult(batch_id, parsed.rows_in_file, len(parsed.observations) - dup, dup)


OBS_COLUMNS = ("source_id", "source_listing_id", "observed_at", "municipality_teryt",
               "municipality_name", "parcel_id", "lat", "lon", "area_m2", "price_pln", "listed_at", "land_use")


def load_observations(conn) -> pd.DataFrame:
    # bez ogłoszeń wyłączonych z analizy (archiwalne itp.): nie trafiają do deduplikacji ani metryk
    cur = conn.execute(f"""SELECT {', '.join('o.' + c for c in OBS_COLUMNS)} FROM core.listing_observations o
                           WHERE NOT EXISTS (SELECT 1 FROM scrape.excluded_listings x
                                             WHERE x.source_id = o.source_id AND x.source_listing_id = o.source_listing_id)""")
    df = pd.DataFrame(cur.fetchall(), columns=list(OBS_COLUMNS))
    for col in ("lat", "lon", "area_m2", "price_pln"):
        df[col] = pd.to_numeric(df[col])
    return df


def run_dedup(conn, params: dedup.DedupParams | None = None) -> tuple[int, list[dedup.Link]]:
    params = params or dedup.DedupParams()
    obs = load_observations(conn)
    records = obs.astype(object).where(obs.notna(), None).to_dict("records")
    listings = dedup.listings_from_observations(records)
    links = dedup.deduplicate(listings, params)
    report = dedup.review(listings, links, params)
    with _committed(conn):
        run_id = conn.execute(
            "INSERT INTO core.dedup_runs (algorithm_version, params, report) VALUES (%s, %s, %s) RETURNING run_id",
            (dedup.ALGORITHM_VERSION, json.dumps(params.as_dict()), json.dumps(report)),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO core.listing_property_links
                       (run_id, source_id, source_listing_id, property_key, match_method, match_confidence)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                [(run_id, l.source_id, l.source_listing_id, l.property_key, l.match_method,
                  l.match_confidence) for l in links],
            )
    return run_id, links


def latest_dedup_run(conn) -> int:
    row = conn.execute("SELECT max(run_id) FROM core.dedup_runs").fetchone()
    if row[0] is None:
        raise RuntimeError("Brak uruchomień deduplikacji — najpierw lmi dedup")
    return row[0]


def run_metrics(conn, run_id: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_id = run_id or latest_dedup_run(conn)
    obs = load_observations(conn)
    cur = conn.execute(
        "SELECT source_id, source_listing_id, property_key FROM core.listing_property_links WHERE run_id = %s",
        (run_id,),
    )
    links = pd.DataFrame(cur.fetchall(), columns=["source_id", "source_listing_id", "property_key"])

    def rows(df: pd.DataFrame, segment: str) -> list[tuple]:
        def py(v):
            if pd.isna(v):
                return None
            return v.item() if hasattr(v, "item") else v  # numpy -> typ Pythona

        return [tuple(py(v) for v in r) + (run_id, segment) for r in df.itertuples(index=False)]

    results = {}
    for segment in metrics.SEGMENTS:
        part = obs if segment == "wszystkie" else obs[obs["land_use"] == segment]
        if part.empty:
            continue
        weekly = metrics.weekly_region_metrics(part, links)
        results[segment] = (weekly, metrics.region_scores(weekly))

    with _committed(conn):
        conn.execute("DELETE FROM mart.weekly_region_metrics")
        conn.execute("DELETE FROM mart.region_scores")
        with conn.cursor() as c:
            for segment, (weekly, scores) in results.items():
                c.executemany(
                    f"""INSERT INTO mart.weekly_region_metrics ({', '.join(weekly.columns)}, dedup_run_id, segment)
                        VALUES ({', '.join(['%s'] * (len(weekly.columns) + 2))})""",
                    rows(weekly, segment),
                )
                c.executemany(
                    f"""INSERT INTO mart.region_scores ({', '.join(scores.columns)}, dedup_run_id, segment)
                        VALUES ({', '.join(['%s'] * (len(scores.columns) + 2))})""",
                    rows(scores, segment),
                )
    return results.get("wszystkie", (pd.DataFrame(), pd.DataFrame()))


def exclude_listings(conn, source_id: str, listing_ids, reason: str) -> int:
    """Wyłącza ogłoszenia z analizy (np. archiwalne). Zwraca liczbę nowo wyłączonych."""
    ids = sorted(set(listing_ids))
    if not ids:
        return 0
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO scrape.excluded_listings (source_id, source_listing_id, reason)
                           VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""", [(source_id, i, reason) for i in ids])
        n = cur.rowcount
    conn.commit()
    return n
