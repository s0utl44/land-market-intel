#!/usr/bin/env bash
# Nocna kopia zapasowa pracawre.com -> Dysk współdzielony Google (szyfrowana AES-256 przed wysłaniem, RODO).
#   radar-baza.dump  – baza radaru (pg_dump),  umowy-dane.tgz – generator (umowy, klienci, pośrednicy, zgłoszenia, wzory),
#   ustawienia.tgz   – pliki .env obu projektów (klucze; potrzebne do odtworzenia serwera).
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
tar -C /opt -czf "$TMP/ustawienia.tgz" lmi/.env umowy/.env
for f in "$TMP/radar-baza.dump" "$TMP/umowy-dane.tgz" "$TMP/ustawienia.tgz"; do
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
