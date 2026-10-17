#!/usr/bin/env python3
"""Zwiad: czy strony ofert Gratki, Nieruchomości-online i Adresowo pokazują zainteresowanie
(wyświetlenia, zapisania/ulubione, obserwujący, kontakty).

Dla każdego portalu: 1 strona wyników + 2 strony ofert (łącznie ok. 9 zapytań, przerwy 4–8 s).
Wypisuje tylko słowo kluczowe, liczbę obok niego i nazwy pól JSON — bez tekstów ogłoszeń i danych osobowych.

Użycie na serwerze:
    docker compose run --rm -T -v "$PWD/scripts:/scripts:ro" --entrypoint python app /scripts/probe_interest.py
"""
import json
import re
import sys

from lmi.scrapers import adresowo, gratka, nonline
from lmi.scrapers.http import PoliteClient
from lmi.scrapers.nuxt import nuxt_data

WORDS = r"wy[sś]wietl\w*|ods[lł]on\w*|obserwuj\w*|zapisa\w*|ulubion\w*|polubie\w*|zainteresowan\w*|kontakt\w* z|" \
        r"views?|viewed|favou?rite\w*|saved|watch\w*|counter|popular\w*"
KEY = re.compile(r'"([A-Za-z_]*(?:view|View|favou?rite|Favou?rite|saved|Saved|watch|Watch|counter|Counter|'
                 r'popular|Popular|visit|Visit|click|Click)[A-Za-z_]*)"\s*:\s*("?[\d.]+"?|null|true|false)')


def scan(html: str) -> None:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = " ".join(re.sub(r"<[^>]+>", " ", text).split())
    hits = []
    for m in re.finditer(WORDS, text, re.I):
        around = text[max(0, m.start() - 40):m.end() + 40]
        nums = re.findall(r"\d[\d\s ]{0,8}", around)
        if nums:
            hits.append((m.group(0).lower(), [n.strip() for n in nums][:3]))
    print("    tekst:", sorted(set((w, tuple(n)) for w, n in hits))[:12] or "brak")
    # krótki fragment wokół "odsłon"/"wyświetl" (same etykiety i liczby, bez treści ogłoszenia)
    for m in list(re.finditer(r"ods[lł]on\w*|wy[sś]wietle\w*", text, re.I))[:3]:
        snip = text[max(0, m.start() - 45):m.end() + 30]
        print("    fragment:", repr(re.sub(r"\b[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,}\s[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,}\b", "<imię>", snip)))
    nd = nuxt_data(html)
    if nd is not None:
        found = []

        def walk(o, path, depth=0):
            if depth > 12 or len(found) > 15:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    if re.search(r"view|odslon|display|statist|counter|popular|favou?rit|observ", k, re.I) and \
                            isinstance(v, (int, float, str)) and re.fullmatch(r"[\d.]+", str(v)):
                        found.append((f"{path}.{k}", v))
                    walk(v, f"{path}.{k}", depth + 1)
            elif isinstance(o, list):
                for i, v in enumerate(o[:5]):
                    walk(v, f"{path}[{i}]", depth + 1)
        walk(nd, "$")
        print("    pola Nuxt (rozpakowane):", [(p[-70:], v) for p, v in found] or "brak")
    else:
        keys = sorted(set(KEY.findall(html)))[:15]
        print("    pola JSON:", keys or "brak")


def main() -> None:
    client = PoliteClient()
    portals = [("gratka", gratka), ("nieruchomosci-online", nonline), ("adresowo", adresowo)]
    only = sys.argv[1:] or [p for p, _ in portals]
    for name, mod in portals:
        if name not in only:
            continue
        print(f"### {name}")
        items, _ = mod.parse_search_page(client.get(mod.search_url("dolnoslaskie", 1)))
        for it in items[:2]:
            print(f"  oferta {it.ad_id}")
            scan(client.get(it.url))
    print("KONIEC")


if __name__ == "__main__":
    main()
