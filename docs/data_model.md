# Model danych

Schemat: `db/init/001_schema.sql` (PostgreSQL 16 + PostGIS). Dwie warstwy:

## `core`: surowe dane, tylko dopisywanie

| Tabela | Zawartość |
|---|---|
| `core.sources` | źródła danych + status zatwierdzenia i podstawa prawna (jedyna tabela core, którą wolno aktualizować) |
| `core.import_batches` | każdy zaimportowany plik: SHA-256, liczba wierszy, dodanych i duplikatów |
| `core.listing_observations` | obserwacje ogłoszeń; `geom` (geography) wyliczane z lat/lon |
| `core.dedup_runs` | każde uruchomienie deduplikacji, wersja algorytmu i parametry (JSON) |
| `core.listing_property_links` | wynik deduplikacji: ogłoszenie → nieruchomość (`property_key`), metoda, pewność |

Triggery blokują `UPDATE`, `DELETE` i `TRUNCATE` na tabelach z danymi. Pomyłki poprawia się nowym importem
lub nowym uruchomieniem deduplikacji, a nie edycją. Dzięki temu każdą liczbę na dashboardzie da się odtworzyć.

`core.sources` ma constraint: źródło nie może być `approved` bez `legal_basis` i `approved_by`.

## `mart`: wyniki, w pełni odtwarzalne

| Tabela | Zawartość |
|---|---|
| `mart.weekly_region_metrics` | metryki tygodniowe per gmina (definicje: `metrics.md`) |
| `mart.region_scores` | ranking gmin |

`lmi metrics` czyści i przelicza obie tabele z najnowszego `dedup_run`. Kolumna `dedup_run_id` mówi, z którego.

## `scrape`: stan scraperów (zmienny)

| Tabela | Zawartość |
|---|---|
| `scrape.otodom_details` | szczegóły oferty Otodom pobrane raz: współrzędne, dokładność pinezki, typ działki |
| `scrape.uldk_communes` | gmina (TERYT) dla punktu, z ULDK (GUGiK) |
| `scrape.runs` | dziennik codziennych przebiegów: status, liczba wierszy, statystyki |

To cache, a nie dane źródłowe. Można go wyczyścić; kolejny przebieg pobierze dane ponownie.

## Przepływ

```
CSV ──lmi validate──▶ (walidacja)
    ──lmi import────▶ core.import_batches + core.listing_observations
                       │
       lmi dedup ──────▶ core.dedup_runs + core.listing_property_links
                       │
       lmi metrics ────▶ mart.weekly_region_metrics + mart.region_scores ──▶ Metabase
```

## Deduplikacja (`src/lmi/dedup.py`)

Ta sama działka bywa wystawiona na kilku portalach albo kilka razy na jednym. Ogłoszenia łączymy, gdy:

| Reguła | Warunek | Pewność |
|---|---|---|
| `parcel_id` | ten sam identyfikator działki | 0,99 |
| `location` | ≤ 150 m i powierzchnia różni się ≤ 5% | 0,85 |
| `price_area` | któreś bez współrzędnych; ta sama gmina, start ≤ 14 dni, powierzchnia i cena ≤ 0,5%, dopasowanie jednoznaczne | 0,60 |

Różne `parcel_id` blokują połączenie. Łączenie jest przechodnie (union-find).

Wynik na danych syntetycznych (seedy 42, 7, 123): precyzja 95–97%, czułość 96–98% (cel PoC: ≥90% / ≥80%).
**Progi są skalibrowane na danych syntetycznych.** Na prawdziwych danych trzeba ręcznie oznaczyć próbkę
(np. 200 par) i sprawdzić je ponownie, bo reguła `price_area` jest najbardziej wrażliwa.
