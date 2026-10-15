"""Wiersz poleceń: python -m lmi <komenda>."""
from __future__ import annotations

import argparse
import logging
import sys

from . import csv_import, dedup, synthetic


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="lmi", description="Land Market Intelligence — PoC")
    p.add_argument("--dsn", help="adres bazy (domyślnie zmienna LMI_DATABASE_URL)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="utwórz schemat w bazie")

    s = sub.add_parser("add-source", help="zarejestruj źródło (niezatwierdzone)")
    s.add_argument("source_id")
    s.add_argument("name")

    s = sub.add_parser("approve-source", help="zatwierdź źródło po sprawdzeniu podstawy prawnej")
    s.add_argument("source_id")
    s.add_argument("--legal-basis", required=True)
    s.add_argument("--approved-by", required=True)

    s = sub.add_parser("validate", help="sprawdź plik CSV bez importu")
    s.add_argument("csv")

    s = sub.add_parser("import", help="zaimportuj plik CSV z danego źródła")
    s.add_argument("source_id")
    s.add_argument("csv")
    s.add_argument("--allow-partial", action="store_true", help="pomiń błędne wiersze zamiast odrzucać plik")

    sub.add_parser("dedup", help="uruchom deduplikację")
    sub.add_parser("metrics", help="przelicz metryki (mart.*)")

    s = sub.add_parser("generate-synthetic", help="wygeneruj dane syntetyczne")
    s.add_argument("out_dir", nargs="?", default="data/synthetic")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--weeks", type=int, default=26)

    s = sub.add_parser("daily", help="codzienny przebieg: scraping Otodom + import + dedup + metryki")
    s.add_argument("--out-dir", default="data/raw")
    s.add_argument("--max-details", type=int, help="limit nowych stron ofert w jednym przebiegu")
    s.add_argument("--region", default="dolnoslaskie", help="slug województwa w adresie Otodom")
    s.add_argument("--teryt-prefix", default="02", help="kod TERYT województwa (filtr gmin)")

    s = sub.add_parser("check-otodom", help="szybki test scrapera bez bazy (wypisuje tylko liczby)")
    s.add_argument("--region", default="dolnoslaskie")

    s = sub.add_parser("demo", help="pełny pipeline na danych syntetycznych")
    s.add_argument("--out-dir", default="data/synthetic")
    s.add_argument("--regions", type=int, default=0, help="liczba losowych gmin zamiast 3 domyślnych")
    s.add_argument("--weeks", type=int, default=26)

    args = p.parse_args(argv)

    if args.cmd == "validate":
        r = csv_import.parse_file(args.csv)
        print(f"Wierszy: {r.rows_in_file}, poprawnych: {len(r.observations)}, błędów: {len(r.errors)}")
        for e in r.errors[:50]:
            print("  " + e)
        return 0 if r.ok else 1

    if args.cmd == "check-otodom":
        from .daily import check_otodom

        return check_otodom(args.region)

    if args.cmd == "generate-synthetic":
        paths = synthetic.generate(args.out_dir, weeks=args.weeks, seed=args.seed)
        for name, path in paths.items():
            print(f"{name}: {path}")
        return 0

    from . import db  # import tutaj, żeby validate/generate działały bez psycopg

    with db.connect(args.dsn) as conn:
        try:
            if args.cmd == "init-db":
                db.apply_schema(conn)
                print("Schemat utworzony.")
            elif args.cmd == "add-source":
                db.add_source(conn, args.source_id, args.name)
                print(f"Źródło {args.source_id} zarejestrowane (niezatwierdzone).")
            elif args.cmd == "approve-source":
                db.approve_source(conn, args.source_id, args.legal_basis, args.approved_by)
                print(f"Źródło {args.source_id} zatwierdzone.")
            elif args.cmd == "import":
                r = db.import_csv(conn, args.source_id, args.csv, allow_partial=args.allow_partial)
                print(f"Batch {r.batch_id}: w pliku {r.rows_in_file}, dodano {r.rows_inserted}, "
                      f"już w bazie {r.rows_duplicate}")
            elif args.cmd == "dedup":
                run_id, links = db.run_dedup(conn)
                print(f"Dedup run {run_id}: {len(links)} ogłoszeń -> "
                      f"{len({l.property_key for l in links})} nieruchomości")
            elif args.cmd == "metrics":
                weekly, scores = db.run_metrics(conn)
                print(f"Zapisano {len(weekly)} wierszy tygodniowych.\n")
                print(scores.to_string(index=False))
            elif args.cmd == "daily":
                from .daily import run_daily

                return run_daily(conn, args.out_dir, args.max_details, args.region, args.teryt_prefix)
            elif args.cmd == "demo":
                return _demo(conn, args.out_dir, args.regions, args.weeks)
        except db.ImportRejected as exc:
            print(f"ODRZUCONO: {exc}", file=sys.stderr)
            return 2
    return 0


def _demo(conn, out_dir: str, n_regions: int = 0, weeks: int = 26) -> int:
    from . import db

    db.apply_schema(conn)
    regions = synthetic.make_regions(n_regions) if n_regions else synthetic.REGIONS
    paths = synthetic.generate(out_dir, weeks=weeks, regions=regions)
    for source_id in synthetic.SOURCES:
        db.add_source(conn, source_id, f"Syntetyczny {source_id}")
        db.approve_source(conn, source_id, "dane syntetyczne (generator)", "demo")
        try:
            r = db.import_csv(conn, source_id, paths[source_id])
            print(f"{source_id}: dodano {r.rows_inserted} obserwacji")
        except db.ImportRejected as exc:
            print(f"{source_id}: pominięto ({exc})")
    run_id, links = db.run_dedup(conn)
    quality = dedup.evaluate(links, synthetic.load_ground_truth(paths["ground_truth"]))
    print(f"Deduplikacja (run {run_id}): precyzja {quality.precision:.1%}, czułość {quality.recall:.1%}")
    _, scores = db.run_metrics(conn, run_id)
    print("\nRanking gmin:\n" + scores.to_string(index=False))
    return 0
