# Format pliku CSV

Jeden plik = jedno źródło. Identyfikator źródła podajesz przy imporcie (`lmi import <source_id> plik.csv`),
nie ma go w pliku. Jeden wiersz to jedno ogłoszenie widziane danego dnia. Przykład: `examples/przyklad.csv`.

| Kolumna | Wymagana | Opis | Walidacja |
|---|---|---|---|
| `source_listing_id` | tak | ID ogłoszenia w źródle | niepuste |
| `observed_at` | tak | dzień obserwacji | `RRRR-MM-DD` |
| `municipality_teryt` | tak | kod TERYT gminy | dokładnie 7 cyfr |
| `municipality_name` | tak | nazwa gminy | niepuste |
| `area_m2` | tak | powierzchnia działki w m² | liczba > 0 |
| `price_pln` | tak | cena ofertowa w zł | liczba > 0 |
| `parcel_id` | nie | identyfikator działki (np. `146501_1.0001.12/3`) | spacje i wielkość liter są ignorowane przy porównaniu |
| `lat`, `lon` | nie | współrzędne WGS84 | obie albo żadna; muszą wypaść w granicach Polski |
| `land_use` | nie | przeznaczenie (budowlana, rolna, …) | — |
| `url`, `title` | nie | link i tytuł ogłoszenia | — |

- Separator: `,` `;` albo tabulator (wykrywany automatycznie). Kodowanie UTF-8 (z BOM lub bez).
- Liczby można zapisać po polsku: `1 234,50`.
- Ten sam `source_listing_id` + `observed_at` dwa razy w pliku to błąd.

## Zasady importu

1. Źródło musi być zarejestrowane **i zatwierdzone** (`lmi approve-source --legal-basis ... --approved-by ...`).
   Bez zatwierdzenia import jest odrzucany (patrz `legal_checklist.md`).
2. Jeśli którykolwiek wiersz jest błędny, odrzucany jest cały plik. `--allow-partial` pomija błędne wiersze.
3. Ten sam plik (identyczny SHA-256) nie wejdzie drugi raz.
4. Wiersze, które już są w bazie (to samo źródło + ID + dzień), są pomijane i liczone jako duplikaty.

Najpierw sprawdź plik bez importu: `lmi validate plik.csv`.
