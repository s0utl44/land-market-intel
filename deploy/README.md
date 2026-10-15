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

## 5. Pierwsze pełne pobranie

Około 4100 ofert. Każdą stronę oferty pobieramy raz, z przerwą 2–4 s. Całość zajmuje około 4 godzin.

```bash
cp deploy/lmi-daily.service deploy/lmi-daily.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start --no-block lmi-daily      # startuje w tle
journalctl -u lmi-daily -f                # podgląd (Ctrl+C nie przerywa pobierania)
```

Jeśli przebieg zostanie przerwany, nic nie przepada: pobrane szczegóły są w cache, a następny przebieg zaczyna od brakujących.

## 6. Codziennie o 8:00

```bash
systemctl enable --now lmi-daily.timer
systemctl list-timers lmi-daily.timer     # pokazuje następne uruchomienie
```

Kolejne przebiegi trwają kilka minut: 58 stron wyników plus szczegóły tylko nowych ofert.

## 7. Dashboard pod domeną (HTTPS + hasło)

Wymaga Traefika działającego na serwerze (entrypoint `websecure`, resolver `letsencrypt`)
i rekordu DNS A domeny wskazującego na IP serwera. Konfiguracja: `docker-compose.web.yml`.

```bash
cd /opt/lmi && git pull
getent hosts pracawre.com                       # musi pokazać IP serwera
read -p "Login do strony: " U && H=$(openssl passwd -apr1) && \
printf "LMI_DOMAIN=pracawre.com\nLMI_BASIC_AUTH='%s:%s'\nCOMPOSE_FILE=docker-compose.yml:docker-compose.web.yml\n" "$U" "$H" >> .env
docker compose up -d metabase
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
cd /opt/lmi && git pull && docker compose build app
```
