# Land Market Intelligence (PoC)

[![testy](https://github.com/s0utl44/land-market-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/s0utl44/land-market-intel/actions/workflows/ci.yml)

System do wykrywania gmin z „gorącym” rynkiem działek. Zbiera ogłoszenia z wielu źródeł, łączy duplikaty
tej samej działki i co tydzień liczy wskaźniki: podaż, tempo znikania ofert, przeceny i ceny za m².
Na tej podstawie tworzy ranking gmin.

![Dashboard](docs/dashboard.png)

*Dashboard Metabase na danych syntetycznych (3 fikcyjne gminy, 26 tygodni).*

## Szybki start

Wymagania: Docker oraz Python 3.11+.

```bash
docker compose up -d db                      # PostgreSQL + PostGIS (schemat tworzy się sam)
pip install -e ".[dev]"
python -m lmi demo                           # dane syntetyczne -> import -> deduplikacja -> metryki

docker compose up -d metabase                # http://localhost:3000
MB_ADMIN_EMAIL=ty@example.com MB_ADMIN_PASSWORD='mocne-haslo' python metabase/setup_dashboard.py
```

## Praca z prawdziwymi danymi

```bash
python -m lmi add-source portal_x "Portal X"
# ...sprawdź docs/legal_checklist.md...
python -m lmi approve-source portal_x --legal-basis "umowa API z 2026-10-01" --approved-by "Jan K."
python -m lmi validate dane.csv
python -m lmi import portal_x dane.csv
python -m lmi dedup
python -m lmi metrics
```

Adres bazy: zmienna `LMI_DATABASE_URL` (domyślnie `postgresql://lmi:lmi@localhost:5432/lmi`).

## Testy

```bash
pytest                                                                  # testy jednostkowe
LMI_TEST_DATABASE_URL=postgresql://lmi:lmi@localhost:5432/lmi pytest    # + integracyjne na PostGIS
```

Testy obejmują walidację CSV, reguły deduplikacji (z progiem jakości: precyzja ≥ 90%, czułość ≥ 80% na 4 seedach),
metryki sprawdzone na ręcznie policzonym przykładzie oraz bazę: append-only, bramkę zatwierdzania źródeł
i ponowny import. GitHub Actions uruchamia całość przy każdym pushu.

## Dokumentacja

- [Model danych i deduplikacja](docs/data_model.md)
- [Format CSV](docs/csv_format.md)
- [Definicje metryk i ograniczenia](docs/metrics.md)
- [Checklista prawna źródeł](docs/legal_checklist.md): **przeczytać przed pobraniem prawdziwych danych**

## Struktura

```
db/init/001_schema.sql     schemat bazy (core append-only + mart)
src/lmi/csv_import.py      parser i walidacja CSV
src/lmi/dedup.py           deduplikacja ogłoszeń
src/lmi/metrics.py         metryki tygodniowe i ranking (DuckDB)
src/lmi/db.py              import, zapis wyników do PostgreSQL
src/lmi/synthetic.py       generator danych testowych
src/lmi/cli.py             komendy `python -m lmi ...`
metabase/                  automatyczna konfiguracja dashboardu
```

## Status

PoC przetestowany end-to-end na danych syntetycznych. Przed produkcją trzeba:
1. pozyskać legalne źródło danych (checklista),
2. skalibrować deduplikację na ręcznie oznaczonej próbce prawdziwych ogłoszeń,
3. wdrożyć na VPS (Docker Compose + Caddy dla HTTPS); Metabase nie może być wystawiony bez HTTPS i silnego hasła.
