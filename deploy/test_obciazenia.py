#!/usr/bin/env python3
"""Test obciążenia pracawre.com: 10, 20 i 30 osób naraz w Leadach, Generatorze umów, Kartotece i Radarze.

Uruchomienie na serwerze (tylko Python ze standardową biblioteką):
    python3 /opt/lmi/deploy/test_obciazenia.py

Tylko ODCZYTY (listy, wyszukiwanie, pulpit) – niczego nie zapisuje ani nie zmienia. Zapytania idą prosto do aplikacji
(127.0.0.1, z pominięciem logowania Google) jako konto testowe, więc mierzą same aplikacje i serwer. Zarządzanie
(Protokoły) nie ma portu na serwerze – go tu nie ma.

Każda „osoba” przez TRWANIE sekund powtarza losowe kliknięcie z listy KLIKNIECIA i odczekuje 0,5–2 s (jak człowiek).
Wynik: dla każdego kliknięcia mediana, 95. percentyl (19 z 20 odpowiedzi szybciej) i najgorszy czas oraz liczba błędów.
"""
from __future__ import annotations

import json
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict

KONTO = "test-obciazenia@wrenieruchomosci.pl"
NAGLOWKI = {"X-Auth-Request-Email": KONTO, "X-Auth-Request-User": KONTO, "X-Pracawre-Poziom": "dostep",
            "Accept-Encoding": "gzip"}
TRWANIE = 30
OSOBY = (10, 20, 30)

# (nazwa, metoda, adres, treść) – typowe kliknięcia; częstsze wpisane kilka razy
KLIKNIECIA = [
    ("Leady: lista", "GET", "http://127.0.0.1:8101/api/leady", None),
    ("Leady: lista", "GET", "http://127.0.0.1:8101/api/leady", None),
    ("Leady: liczby na pulpicie", "GET", "http://127.0.0.1:8101/api/pulpit", None),
    ("Leady: dane konta", "GET", "http://127.0.0.1:8101/api/ja", None),
    ("Umowy: Otwórz… (lista umów)", "POST", "http://127.0.0.1:8090/api/listaKompletow", []),
    ("Umowy: strona", "GET", "http://127.0.0.1:8090/", None),
    ("Kartoteka: szukaj osoby", "GET", "http://127.0.0.1:8098/api/szukaj?typ=osoby&q=a&limit=50", None),
    ("Kartoteka: szukaj mieszkania", "GET", "http://127.0.0.1:8098/api/szukaj?typ=mieszkania&q=wroc&limit=50", None),
    ("Radar: ranking gmin", "GET", "http://127.0.0.1:8080/api/ranking", None),
]


def klik(metoda: str, adres: str, tresc) -> tuple[float, str | None]:
    dane = json.dumps(tresc).encode() if tresc is not None else None
    req = urllib.request.Request(adres, data=dane, method=metoda,
                                 headers={**NAGLOWKI, **({"Content-Type": "application/json"} if dane else {})})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
        return time.perf_counter() - start, None
    except urllib.error.HTTPError as e:
        return time.perf_counter() - start, f"HTTP {e.code}"
    except Exception as e:                      # brak połączenia, przekroczony czas
        return time.perf_counter() - start, e.__class__.__name__


def osoba(koniec: float, wyniki: dict, bledy: dict, zamek: threading.Lock):
    while time.monotonic() < koniec:
        nazwa, metoda, adres, tresc = random.choice(KLIKNIECIA)
        czas, blad = klik(metoda, adres, tresc)
        with zamek:
            (bledy[nazwa].append(blad) if blad else wyniki[nazwa].append(czas))
        time.sleep(random.uniform(0.5, 2.0))


def runda(ile: int) -> None:
    wyniki, bledy, zamek = defaultdict(list), defaultdict(list), threading.Lock()
    koniec = time.monotonic() + TRWANIE
    watki = [threading.Thread(target=osoba, args=(koniec, wyniki, bledy, zamek)) for _ in range(ile)]
    for w in watki:
        w.start()
    for w in watki:
        w.join()
    print(f"\n=== {ile} osób naraz przez {TRWANIE} s ===")
    print(f"{'kliknięcie':34}{'ile':>6}{'mediana':>10}{'95%':>9}{'najgorzej':>11}  błędy")
    for nazwa in dict.fromkeys(k[0] for k in KLIKNIECIA):
        c = sorted(wyniki[nazwa])
        if not c:
            print(f"{nazwa:34}{0:>6}{'–':>10}{'–':>9}{'–':>11}  {len(bledy[nazwa])} {sorted(set(bledy[nazwa]))}")
            continue
        p95 = c[min(len(c) - 1, int(len(c) * 0.95))]
        print(f"{nazwa:34}{len(c):>6}{statistics.median(c):>9.2f}s{p95:>8.2f}s{c[-1]:>10.2f}s  "
              + (f"{len(bledy[nazwa])} {sorted(set(bledy[nazwa]))}" if bledy[nazwa] else "–"))


if __name__ == "__main__":
    print(__doc__.split("\n\n")[0])
    for ile in OSOBY:
        runda(ile)
    print("\nDobrze: mediana poniżej 0,3 s i 95% poniżej 1 s przy 30 osobach. Wynik wklej do rozmowy z Claude.")
