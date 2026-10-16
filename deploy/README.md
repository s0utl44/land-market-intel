# Wdrożenie na VPS (Hetzner)

Wszystkie komendy wykonuje się na serwerze jako root (albo z `sudo`). Wymagany jest Docker z pluginem `compose`.

## 1. Kod i hasła

```bash
git clone https://github.com/s0utl44/land-market-intel.git /opt/lmi
cd /opt/lmi
# silne hasło do bazy (zapisz je też w menedżerze haseł)
echo "LMI_DB_PASSWORD=$(openssl rand -hex 24)" > .env
chmod 600 .env
```

> Jeśli repo jest prywatne, `git clone` wymaga tokenu GitHub (fine-grained, tylko odczyt tego repo):
> `git clone https://<TOKEN>@github.com/s0utl44/land-market-intel.git /opt/lmi`

## 2. Baza, obraz aplikacji, Metabase

```bash
docker compose up -d db metabase
docker compose build app
docker compose run --rm app init-db
```

## 3. Szybki test scrapera (bez bazy, ~10 zapytań)

```bash
docker compose run --rm app check-otodom
```

Ostatnia linia ma brzmieć `WYNIK: OK`. W przeciwnym razie wklej wynik do czatu.

## 4. Zatwierdzenie źródła (jednorazowo)

```bash
docker compose run --rm app add-source otodom Otodom
docker compose run --rm app approve-source otodom \
  --legal-basis "prywatne narzędzie; regulamin przeczytany, ryzyko przyjęte" --approved-by "<Twoje imię>"
```

## 4b. Kolejne portale (Gratka)

Każdy portal to osobne źródło: blokada jednego nie zatrzymuje pozostałych.

```bash
docker compose run --rm app check-gratka        # test: 1 strona + 3 oferty, tylko liczby
docker compose run --rm app add-source gratka Gratka
docker compose run --rm app approve-source gratka \
  --legal-basis "prywatne narzędzie; regulamin przeczytany, ryzyko przyjęte" --approved-by "<Twoje imię>"
```

Codzienny przebieg obejmuje wszystkie zatwierdzone portale z listy `LMI_SOURCES`
(domyślnie `otodom,gratka`). Jeden portal można uruchomić osobno: `lmi daily --sources gratka`.

## 5. Pierwsze pełne pobranie

Około 4100 ofert. Każdą stronę oferty pobieramy raz, z przerwą 2–4 s. Całość zajmuje około 4 godzin.

```bash
cp deploy/lmi-daily.service deploy/lmi-daily.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start --no-block lmi-daily      # startuje w tle
journalctl -u lmi-daily -f                # podgląd (Ctrl+C nie przerywa pobierania)
```

Jeśli przebieg zostanie przerwany, nic nie przepada: pobrane szczegóły są w cache, a następny przebieg zaczyna od brakujących.

## 6. Codziennie o 8:00 (+ ponowna próba o 14:00)

```bash
systemctl enable --now lmi-daily.timer
# ponowna próba o 14:00, tylko jeśli poranne pobieranie się nie udało (np. chwilowa blokada 403)
cp deploy/lmi-daily-retry.service deploy/lmi-daily-retry.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now lmi-daily-retry.timer
systemctl list-timers lmi-daily.timer     # pokazuje następne uruchomienie
```

Kolejne przebiegi trwają kilka minut: 58 stron wyników plus szczegóły tylko nowych ofert.

## 7. Strona pod domeną (HTTPS + hasło)

- `https://pracawre.com/`: Radar Działek (usługa `web`)
- `https://pracawre.com/metabase/`: Metabase do własnych analiz

Wymaga Traefika działającego na serwerze (entrypoint `websecure`, resolver `letsencrypt`)
i rekordu DNS A domeny wskazującego na IP serwera. Konfiguracja: `docker-compose.web.yml`.

```bash
cd /opt/lmi && git pull
getent hosts pracawre.com                       # musi pokazać IP serwera
read -p "Login do strony: " U && H=$(openssl passwd -apr1) && \
printf "LMI_DOMAIN=pracawre.com\nLMI_BASIC_AUTH='%s:%s'\nCOMPOSE_FILE=docker-compose.yml:docker-compose.web.yml\n" "$U" "$H" >> .env
docker compose build web
docker compose up -d web metabase
```

`openssl` dwa razy zapyta o hasło (nie zostaje w historii poleceń). Wejście na stronę wymaga
tego loginu i hasła, a potem osobnego logowania do Metabase. Certyfikat HTTPS Traefik pobiera
sam przy pierwszym wejściu (do minuty).

### Bez domeny: tunel SSH

Metabase nasłuchuje też na `localhost` serwera. Z własnego komputera łączysz się tunelem SSH:

```bash
ssh -L 3000:localhost:3000 root@<IP-serwera>
# potem w przeglądarce: http://localhost:3000
```

Pierwsza konfiguracja dashboardu (na serwerze):

```bash
docker compose run --rm --entrypoint python -e MB_URL=http://metabase:3000 \
  -e MB_ADMIN_EMAIL=<email> -e MB_ADMIN_PASSWORD='<hasło>' -e LMI_DB_PASSWORD="$(grep -oP '(?<=LMI_DB_PASSWORD=).*' .env)" \
  -v "$PWD/metabase:/app/metabase" app metabase/setup_dashboard.py
```

### Logowanie kontem Google (zamiast hasła w okienku)

Wpuszcza tylko konta z domeny firmy (`wrenieruchomosci.pl`, zmiana: `LMI_EMAIL_DOMAIN` w `.env`).
Konfiguracja: `docker-compose.google.yml`, polskie ekrany logowania: `deploy/oauth2/templates/`.

**1. Google Cloud (jednorazowo, ok. 10 minut)**, zalogowany kontem administratora Google Workspace firmy:

1. Wejdź na https://console.cloud.google.com i utwórz projekt, np. „Radar Dzialek”.
2. Menu → **Google Auth Platform** (dawniej „Ekran zgody OAuth”) → **Rozpocznij**:
   nazwa aplikacji „Radar Działek”, e-mail pomocy, **Odbiorcy: Wewnętrzni** (tylko konta firmy), e-mail kontaktowy.
3. **Klienci** → **Utwórz klienta** → typ **Aplikacja internetowa**, nazwa „pracawre.com”,
   **Autoryzowane identyfikatory URI przekierowania**: `https://pracawre.com/oauth2/callback` → **Utwórz**.
4. Skopiuj **Identyfikator klienta** i **Tajny klucz klienta**.

**2. Serwer:**

```bash
cd /opt/lmi && git pull && docker compose build web
read -p "Identyfikator klienta: " CID && read -s -p "Tajny klucz klienta: " CS && echo && \
printf "GOOGLE_CLIENT_ID=%s\nGOOGLE_CLIENT_SECRET=%s\nOAUTH2_COOKIE_SECRET=%s\n" "$CID" "$CS" "$(openssl rand -base64 32 | tr -- '+/' '-_')" >> .env
sed -i 's|^COMPOSE_FILE=.*|COMPOSE_FILE=docker-compose.yml:docker-compose.web.yml:docker-compose.google.yml|' .env
docker compose up -d web metabase oauth2-proxy
```

Powrót do hasła w okienku: w `.env` ustaw z powrotem
`COMPOSE_FILE=docker-compose.yml:docker-compose.web.yml`, potem
`docker compose up -d web metabase --remove-orphans`.

Metabase (`/metabase`) ma dodatkowo własne konto, niezależne od logowania Google.

### Dostęp dla kolejnej osoby z zespołu (tryb hasła w okienku)

Każda osoba ma własny login do bramki. Dodanie osoby (pyta o login i dwa razy o hasło):

```bash
cd /opt/lmi
read -p "Login: " U && H=$(openssl passwd -apr1) && \
sed -i "s|^LMI_BASIC_AUTH='\(.*\)'|LMI_BASIC_AUTH='\1,$U:$H'|" .env && docker compose up -d web metabase
```

Usunięcie osoby: otwórz `.env` (`nano .env`), w linii `LMI_BASIC_AUTH` usuń fragment `,login:skrót`
tej osoby i uruchom `docker compose up -d web metabase`.

## Historia ofert z konta Otodom (opcjonalnie)

Historię ogłoszenia (wystawienie, zmiany cen, zdjęcia i ponowne wystawienia) oraz liczbę wyświetleń
i zapisań Otodom pokazuje tylko zalogowanym. Radar korzysta z sesji osobnego konta: program się
nie loguje, tylko używa ciasteczka skopiowanego z przeglądarki.

1. Zaloguj się na Otodom w Chrome, otwórz dowolne ogłoszenie, **F12** → **Network** → **F5** →
   pierwszy wiersz → **Headers** → **Request Headers** → wiersz `cookie` → prawy przycisk → **Copy value**.
2. Na serwerze (edytor nano, bo terminal obcina wklejane linie dłuższe niż 4095 znaków):
   ```bash
   cd /opt/lmi && mkdir -p data && nano data/otodom-cookie    # wklej, Ctrl+O, Enter, Ctrl+X
   chmod 600 data/otodom-cookie && wc -c < data/otodom-cookie  # powinno być > 4095
   ```

Codzienny przebieg pobiera historię dla nowych ofert i uzupełnia ją dla 150 starszych dziennie
(`lmi daily --history-backfill N` zmienia limit; więcej = szybciej, ale większe ryzyko blokady 403). Gdy sesja wygaśnie, przebieg działa dalej bez historii,
a na stronie pojawia się ostrzeżenie. Wtedy powtórz kroki 1–2.

## Monitoring

| Kod wyjścia `lmi daily` | Znaczenie |
|---|---|
| 0 | OK |
| 2 | źródło niezatwierdzone |
| 3 | Otodom zablokował dostęp (403). Przebieg przerwany, bez ponawiania |
| 4 | Otodom zmienił strukturę strony, parser do poprawki |
| 5 | liczba ofert spadła o ponad połowę względem poprzedniego dnia |

```bash
systemctl status lmi-daily                 # ostatni przebieg
journalctl -u lmi-daily --since today      # log z dziś
docker compose exec db psql -U lmi -d lmi -c \
  "SELECT started_at, status, rows_written, message FROM scrape.runs ORDER BY run_id DESC LIMIT 10"
```

Hermes może co rano sprawdzać `systemctl is-failed lmi-daily` i dać znać, gdy przebieg się nie udał.

## Aktualizacja kodu

```bash
cd /opt/lmi && git pull && docker compose build app web && docker compose up -d web
```
