# Checklista prawna źródeł danych

> To lista kontrolna, a nie porada prawna. Przed komercyjnym użyciem skonsultuj się z prawnikiem.

Źródło można zatwierdzić (`lmi approve-source`) dopiero po odhaczeniu wszystkich punktów.
W `--legal-basis` wpisz konkretną podstawę, np. „umowa API z 2026-10-01, §3”.

## Portale ogłoszeniowe

- [ ] Przeczytany aktualny regulamin. Zapisz datę i kopię (PDF).
- [ ] Czy regulamin zakazuje scrapowania lub automatycznego pobierania? Jeśli tak, potrzebna jest umowa albo oficjalne API.
- [ ] Czy istnieje oficjalne API, feed partnerski lub licencja na dane? To najbezpieczniejsza droga.
- [ ] Prawo sui generis do baz danych (ustawa o ochronie baz danych): czy pobieramy „istotną część” bazy?
- [ ] `robots.txt` i limity zapytań. Nie obciążać serwisu.
- [ ] **RODO**: ogłoszenia zawierają dane osobowe (telefon, imię, nazwisko). Nie importujemy ich, bo format CSV ich nie przewiduje.
      Nie przechowujemy też opisów ani zdjęć.
- [ ] Prawa autorskie do opisów i zdjęć: nie kopiujemy ich, zapisujemy tylko fakty (cena, powierzchnia, lokalizacja).

## RCN (Rejestr Cen Nieruchomości)

- [ ] Ustalić aktualny tryb dostępu: udostępnianie przez starostwo lub urząd miasta (wniosek, opłaty) albo usługi
      krajowe (geoportal / GUGiK). Zasady zmieniały się w ostatnich latach, więc sprawdź je u źródła.
- [ ] Warunki licencji: czy dane można przetwarzać komercyjnie i publikować w formie zagregowanej?
- [ ] Dane osobowe stron transakcji nie mogą trafić do systemu.

## Dane publiczne (GUS, TERYT, PRG)

- [ ] Sprawdzić licencję (zwykle otwarta, z wymogiem podania źródła) i dodać atrybucję na dashboardzie.
