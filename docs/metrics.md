# Definicje metryk

Liczone w DuckDB (`src/lmi/metrics.py`) na **nieruchomościach po deduplikacji**, nie na ogłoszeniach.
Tydzień zaczyna się w poniedziałek.

| Metryka | Definicja |
|---|---|
| `active_supply` | nieruchomości aktywne w tygodniu: od pierwszego do ostatniego tygodnia, w którym je widziano. Luka w scrapowaniu nie przerywa aktywności. |
| `new_listings` | nieruchomości widziane pierwszy raz w tym tygodniu |
| `disappeared_listings` | nieruchomości, których ostatni tydzień widoczności to poprzedni tydzień. Nie liczy się zniknięć w ostatnim tygodniu danych, bo jeszcze ich nie znamy. |
| `median_price_per_m2` | mediana zł/m² aktywnych nieruchomości, wg ostatniej znanej ceny |
| `discounted_share` | odsetek aktywnych nieruchomości, których bieżąca cena jest ≥ 1% niższa od ceny początkowej |
| `absorption_rate` | `disappeared_listings` / `active_supply` z poprzedniego tygodnia |
| `median_days_to_disappear` | mediana dni od pierwszej do ostatniej obserwacji dla nieruchomości znikniętych w tym tygodniu |

## Ranking (`mart.region_scores`)

Dla każdej gminy: średnia absorpcja, trend ceny (średnia mediana zł/m² z ostatnich 4 tygodni do pierwszych 4),
średni odsetek przecenionych, mediana dni do zniknięcia. Dla każdej cechy liczony jest z-score względem pozostałych gmin, a potem

```
opportunity_score = (z_absorpcja + z_trend_cen − z_przecenione − z_dni_do_zniknięcia) / 4
```

Score jest **względny**: porównuje gminy w tym samym zbiorze, a nie ocenia ich bezwzględnie. Wagi są równe i arbitralne.

## Ograniczenia, które trzeba znać

- **Zniknięcie ≠ sprzedaż.** Ogłoszenie mogło zostać wycofane, wygasnąć albo przenieść się na nieobserwowany portal.
  Do weryfikacji potrzebne są transakcje z RCN.
- **Pierwszy tydzień danych**: cała istniejąca podaż wygląda na „nową”. Ranking pomija pierwszy tydzień.
- **Cenzurowanie z lewej**: nieruchomości widoczne od pierwszego tygodnia nie wchodzą do `median_days_to_disappear`,
  bo nie znamy ich prawdziwego początku. Na początku okresu ta metryka jest zaniżona, bo zdążyły zniknąć tylko szybkie oferty.
  Wiarygodna staje się po kilku miesiącach danych.
- **Trend ceny jest szumny** przy małej liczbie ofert (~100 na gminę) i mieszanych typach działek
  (budowlane i rolne razem). W kolejnej fazie warto liczyć go osobno per `land_use`.
- To ceny **ofertowe**, nie transakcyjne.
