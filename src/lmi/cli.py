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
    sub.add_parser("refresh-page", help="przelicz od razu gotowe dane strony (Co się zmieniło, transakcje RCN)")
    sub.add_parser("nonline-archived", help="jednorazowo: wyłącz z analizy archiwalne ogłoszenia Nieruchomości-online")
    sub.add_parser("dedup-review", help="raport jakości ostatniej deduplikacji z linkami (możliwe duplikaty, błędy)")
    s = sub.add_parser("dedup-diff", help="co rozdzieliła nowa deduplikacja względem poprzedniej (z powodami)")
    s.add_argument("--old", type=int, help="run_id starszej deduplikacji (domyślnie przedostatnia)")
    s.add_argument("--new", type=int, help="run_id nowszej (domyślnie ostatnia)")

    s = sub.add_parser("generate-synthetic", help="wygeneruj dane syntetyczne")
    s.add_argument("out_dir", nargs="?", default="data/synthetic")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--weeks", type=int, default=26)

    s = sub.add_parser("daily", help="codzienny przebieg: scraping Otodom + import + dedup + metryki")
    s.add_argument("--out-dir", default="data/raw")
    s.add_argument("--max-details", type=int, help="limit nowych stron ofert w jednym przebiegu")
    s.add_argument("--region", default="dolnoslaskie", help="slug województwa w adresie Otodom")
    s.add_argument("--teryt-prefix", default="02", help="kod TERYT województwa (filtr gmin)")
    s.add_argument("--history-backfill", type=int, default=150,
                   help="ile wcześniej pobranych ofert uzupełnić o historię z konta Otodom (domyślnie 150)")
    s.add_argument("--sources", help="źródła po przecinku, np. gratka albo otodom,gratka (domyślnie wszystkie)")
    s.add_argument("--if-needed", action="store_true",
                   help="uruchom tylko, jeśli dzisiejsze pobieranie jeszcze się nie udało (ponowna próba)")

    s = sub.add_parser("rcn", help="ceny transakcyjne z RCN (geoportal): pierwsze pobranie albo odświeżenie")
    s.add_argument("--teryt-prefix", default="02", help="województwo (TERYT), domyślnie dolnośląskie")
    s.add_argument("--since", help="od daty aktu RRRR-MM-DD (domyślnie: od ostatniego znanego minus 120 dni)")
    s.add_argument("--repair", action="store_true",
                   help="tylko ponów kawałki zapisane jako luki (bez pobierania całych miesięcy)")

    s = sub.add_parser("rcn-coverage", help="kompletność RCN per powiat: usługa vs baza (do porównań)")
    s.add_argument("--since", default="2024-01-01")

    s = sub.add_parser("feedback", help="zgłoszenia ze strony jako tekst do skopiowania")
    s.add_argument("--wszystkie", action="store_true", help="także oznaczone jako zrobione")

    s = sub.add_parser("check-otodom", help="szybki test scrapera bez bazy (wypisuje tylko liczby)")
    s.add_argument("--region", default="dolnoslaskie")

    s = sub.add_parser("check-gratka", help="szybki test scrapera Gratki bez bazy (wypisuje tylko liczby)")
    s.add_argument("--region", default="dolnoslaskie")

    s = sub.add_parser("check-nonline", help="szybki test scrapera Nieruchomości-online bez bazy")
    s.add_argument("--region", default="dolnoslaskie")

    s = sub.add_parser("check-adresowo", help="szybki test scrapera Adresowo bez bazy")
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

    if args.cmd == "check-gratka":
        from .scrapers import gratka

        return gratka.check(args.region)

    if args.cmd == "check-adresowo":
        from .scrapers import adresowo

        return adresowo.check(args.region)

    if args.cmd == "check-nonline":
        from .scrapers import nonline

        return nonline.check(args.region)

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
            elif args.cmd == "nonline-archived":
                from . import jobs, web
                from .scrapers import nonline
                from .scrapers.http import PoliteClient

                with jobs.tracked(conn, "nonline-archived", "lista archiwalnych ogłoszeń") as job:
                    ids, pages = nonline.archived_ids(PoliteClient().get)
                    n = db.exclude_listings(conn, "nieruchomosci-online", ids, "archiwalne")
                    run_id, links = db.run_dedup(conn)
                    db.run_metrics(conn, run_id)
                    web.refresh_changes(conn)
                    job.finish("ok", f"{pages} stron, archiwalnych {len(set(ids))}, nowo wyłączonych {n}")
                print(f"Nieruchomości-online: {pages} stron listy, archiwalnych {len(set(ids))}, nowo wyłączonych {n}. "
                      f"Deduplikacja: {len(links)} ogłoszeń -> {len({l.property_key for l in links})} działek.")
            elif args.cmd == "dedup-review":
                from . import dedup

                obs = db.load_observations(conn)
                listings = dedup.listings_from_observations(obs.astype(object).where(obs.notna(), None).to_dict("records"))
                run_id = db.latest_dedup_run(conn)
                links = [dedup.Link(s_, l, p, m, c) for s_, l, p, m, c in conn.execute(
                    """SELECT source_id, source_listing_id, property_key, match_method, match_confidence
                       FROM core.listing_property_links WHERE run_id = %s""", (run_id,))]
                rep = dedup.review(listings, links, examples=8)
                urls = {f"{s_}:{l}": u for s_, l, u in conn.execute(
                    """SELECT DISTINCT ON (source_id, source_listing_id) source_id, source_listing_id, url
                       FROM core.listing_observations ORDER BY source_id, source_listing_id, observed_at DESC""")}
                print(f"Deduplikacja run {run_id}: {rep['listings']} ogłoszeń -> {rep['properties']} działek, "
                      f"z kilku ogłoszeń: {rep['multi_listing_properties']}")
                print(f"{'portal':<22}{'ogłoszeń':>9}{'działek':>9}{'tylko tu':>10}")
                for src, v in rep["by_source"].items():
                    print(f"{src:<22}{v['listings']:>9}{v['properties']:>9}{v['only_this_portal']:>10}")
                for key, title in (("possible_same_source", "Możliwe duplikaty w jednym portalu (nie połączone)"),
                                   ("possible_cross_source", "Możliwe duplikaty między portalami (nie połączone)")):
                    print(f"\n{title}: {rep[key]}")
                    for e in rep[key + "_examples"]:
                        print(f"  {e['area']:.0f} m², {e['prices'][0]:.0f} / {e['prices'][1]:.0f} zł, "
                              f"pinezki {e['dist_m'] if e['dist_m'] is not None else '–'} m, typ {e['land_use'][0]}/{e['land_use'][1]}")
                        print(f"      {urls.get(e['a'], e['a'])}\n      {urls.get(e['b'], e['b'])}")
                print(f"\nDo sprawdzenia (połączone, a ceny/metraże się różnią): {rep['suspicious']}, "
                      f"nieprawdopodobne wartości: {rep['outliers']}")
            elif args.cmd == "dedup-diff":
                from . import dedup

                runs = [r for (r,) in conn.execute("SELECT run_id FROM core.dedup_runs ORDER BY run_id DESC LIMIT 2")]
                new_id, old_id = args.new or runs[0], args.old or runs[1]
                load = lambda rid: {(s_, l): p for s_, l, p in conn.execute(
                    "SELECT source_id, source_listing_id, property_key FROM core.listing_property_links WHERE run_id = %s",
                    (rid,))}
                obs = db.load_observations(conn)
                listings = dedup.listings_from_observations(obs.astype(object).where(obs.notna(), None).to_dict("records"))
                diff = dedup.diff_runs(listings, load(old_id), load(new_id))
                print(f"Pary połączone w run {old_id}, a rozdzielone w run {new_id}: {sum(v['pairs'] for v in diff.values())}")
                for why, v in diff.items():
                    print(f"\n{v['pairs']:>6}  {why}")
                    for e in v["examples"]:
                        print(f"        {e['a']} + {e['b']}: {e['areas'][0]:.0f}/{e['areas'][1]:.0f} m², "
                              f"{e['prices'][0]:.0f}/{e['prices'][1]:.0f} zł, typ {e['land_use'][0]}/{e['land_use'][1]}, "
                              f"pinezki {e['dist_m'] if e['dist_m'] is not None else '–'} m · {e['why']}")
            elif args.cmd == "refresh-page":
                from . import rcn, web

                rcn.refresh_land(conn)
                web.refresh_changes(conn)
                print("Dane strony przeliczone (transakcje RCN i Co się zmieniło dla 1 / 7 / 30 dni).")
            elif args.cmd == "metrics":
                weekly, scores = db.run_metrics(conn)
                print(f"Zapisano {len(weekly)} wierszy tygodniowych.\n")
                print(scores.to_string(index=False))
            elif args.cmd == "daily":
                from .daily import run_daily

                return run_daily(conn, args.out_dir, args.max_details, args.region, args.teryt_prefix,
                                 history_backfill=args.history_backfill, if_needed=args.if_needed,
                                 sources=tuple(args.sources.split(",")) if args.sources else None)
            elif args.cmd == "rcn":
                from datetime import date as _date

                from . import rcn

                from . import jobs

                with jobs.tracked(conn, "rcn", "naprawa luk" if args.repair else "pobieranie aktów z geoportalu") as job:
                    n = 0
                    if not args.repair:
                        n = rcn.refresh(conn, teryt_prefix=args.teryt_prefix,
                                        since=_date.fromisoformat(args.since) if args.since else None)
                    fixed, gaps = rcn.repair(conn, teryt_prefix=args.teryt_prefix)
                    job.finish("warning" if gaps else "ok", f"zapisano {n} rekordów, naprawiono luk: {fixed}"
                               + (f", zostało luk: {gaps}" if gaps else ""))
                print(f"RCN: naprawiono luk: {fixed}, zostało: {gaps}")
                land = conn.execute("SELECT count(*), max(doc_date) FROM mart.rcn_land_transactions "
                                    "WHERE gmina_teryt LIKE %s", (args.teryt_prefix + "%",)).fetchone()
                print(f"RCN: zapisano {n} rekordów działek; transakcji samym gruntem w bazie: {land[0]} "
                      f"(ostatni akt: {land[1]})")
                for *_, g in conn.execute(rcn.LATEST_WITH_GAPS, (args.teryt_prefix + "%",)):
                    print("  luka w usłudze geoportalu:", g[:300] + ("…" if len(g) > 300 else ""))
            elif args.cmd == "rcn-coverage":
                from datetime import date as _date

                from . import rcn

                print(f"{'powiat':<7}{'w usłudze':>11}{'w bazie':>10}{'transakcji':>12}{'gruntowych':>12}  uwagi")
                tot = [0, 0, 0, 0]
                for c in rcn.coverage(conn, since=_date.fromisoformat(args.since)):
                    note = "BRAK W USŁUDZE" if c["service"] == 0 else (
                        "niepełne w bazie" if c["db_rows"] < c["service"] else "")
                    print(f"{c['powiat']:<7}{c['service']:>11}{c['db_rows']:>10}{c['db_tx']:>12}{c['land_tx']:>12}  {note}")
                    for i, k in enumerate(("service", "db_rows", "db_tx", "land_tx")):
                        tot[i] += c[k]
                print(f"{'razem':<7}{tot[0]:>11}{tot[1]:>10}{tot[2]:>12}{tot[3]:>12}")
            elif args.cmd == "feedback":
                import os as _os

                from . import web

                _os.environ.setdefault("LMI_DATABASE_URL", conn.info.dsn)
                print(web.feedback_text(web.feedback_rows(None if args.wszystkie else "nowe")), end="")
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
