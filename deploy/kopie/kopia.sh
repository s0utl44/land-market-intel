#!/usr/bin/env bash
# Nocna kopia zapasowa pracawre.com -> Dysk współdzielony Google (szyfrowana AES-256 przed wysłaniem, RODO).
#   radar-baza.dump  – baza radaru (pg_dump),  umowy-dane.tgz – generator (umowy, klienci, pośrednicy, zgłoszenia, wzory),
#   protokoly-baza.dump, protokoly-zdjecia.tgz – protokoły WRE (baza i zdjęcia), kartoteka-baza.tgz – kartoteka (gzip SQLite),
#   ustawienia.tgz   – pliki .env projektów (klucze; potrzebne do odtworzenia serwera).
# Rotacja: dzienne/<data> przez 14 dni, miesieczne/<rok-mies> (z 1. dnia miesiąca) przez ok. rok.
# Ustawienia w /opt/kopie: google.json (klucz konta usługi), haslo (hasło szyfrowania), ustawienia (DYSK_ID=...).
# Odtworzenie: deploy/kopie/README.md.
set -euo pipefail
K=/opt/kopie
# shellcheck source=/dev/null
source "$K/ustawienia"
: "${DYSK_ID:?ustaw DYSK_ID w /opt/kopie/ustawienia}"
DZIS=$(date +%F)
TMP=$(mktemp -d "$K/tmp.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

(cd /opt/lmi && docker compose exec -T db pg_dump -U lmi -Fc lmi) > "$TMP/radar-baza.dump"
tar -C /opt -czf "$TMP/umowy-dane.tgz" umowy-dane
# protokoły (jeśli zainstalowane): baza + zdjęcia
if [ -d /opt/protokoly ]; then
  (cd /opt/protokoly && docker compose exec -T db pg_dump -U protokoly -Fc protokoly) > "$TMP/protokoly-baza.dump"
  tar -C /opt -czf "$TMP/protokoly-zdjecia.tgz" protokoly-dane
fi
# kartoteka (wspólna baza osób i mieszkań): spójna kopia SQLite przez backup API w kontenerze
if [ -d /opt/kartoteka ]; then
  (cd /opt/kartoteka && docker compose exec -T kartoteka python -c "import sqlite3; d = sqlite3.connect('/dane/.kopia.db'); sqlite3.connect('/dane/kartoteka.db').backup(d); d.close()")
  mv /opt/kartoteka-dane/.kopia.db "$TMP/kartoteka.db" && gzip -c "$TMP/kartoteka.db" > "$TMP/kartoteka-baza.tgz" && rm "$TMP/kartoteka.db"
fi
# podejrzanie mała kopia (pusta baza, błąd zrzutu) = przerwanie, zanim rotacja usunie dobre starsze kopie
za_mala() { [ "$(stat -c %s "$1")" -lt "$2" ] && { echo "BŁĄD: $(basename "$1") ma tylko $(stat -c %s "$1") B" >&2; exit 1; }; return 0; }
za_mala "$TMP/radar-baza.dump" 1000000
za_mala "$TMP/umowy-dane.tgz" 10000
[ -f "$TMP/protokoly-baza.dump" ] && za_mala "$TMP/protokoly-baza.dump" 2000
tar -C /opt -czf "$TMP/ustawienia.tgz" lmi/.env umowy/.env $( [ -f /opt/protokoly/.env ] && echo protokoly/.env ) $( [ -f /opt/kartoteka/.env ] && echo kartoteka/.env )
for f in "$TMP"/*.dump "$TMP"/*.tgz; do
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$K/haslo" -in "$f" -out "$f.enc"
  rm "$f"
done
(cd "$TMP" && sha256sum ./*.enc > sumy.txt)

rclone() {
  docker run --rm -v "$K/google.json:/google.json:ro" -v "$TMP:/dane:ro" \
    -e RCLONE_CONFIG_GD_TYPE=drive -e RCLONE_CONFIG_GD_SCOPE=drive \
    -e RCLONE_CONFIG_GD_SERVICE_ACCOUNT_FILE=/google.json -e RCLONE_CONFIG_GD_TEAM_DRIVE="$DYSK_ID" \
    rclone/rclone:1.68 "$@"
}
rclone copy /dane "gd:dzienne/$DZIS"
if [ "$(date +%d)" = "01" ]; then rclone copy /dane "gd:miesieczne/$(date +%Y-%m)"; fi
rclone delete --min-age 15d gd:dzienne && rclone rmdirs --leave-root gd:dzienne
rclone delete --min-age 400d gd:miesieczne && rclone rmdirs --leave-root gd:miesieczne
echo "kopia $DZIS: OK ($(du -ch "$TMP"/*.enc | tail -1 | cut -f1))"
