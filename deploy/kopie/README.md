# Kopia zapasowa pracawre.com na Dysk Google

Co noc o 02:40 `kopia.sh` wysyła na Dysk współdzielony Google trzy zaszyfrowane pliki (AES-256, hasło tylko na
serwerze i w menedżerze haseł): bazę radaru, dane generatora umów i pliki `.env`. Dzienne zostają 14 dni,
miesięczne (z 1. dnia miesiąca) około roku. Dysk widzi tylko zaszyfrowane pliki — bez hasła nie da się ich odczytać.

## Odtworzenie
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in umowy-dane.tgz.enc | tar -C /opt -xz
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in radar-baza.dump.enc > radar.dump
cd /opt/lmi && docker compose exec -T db pg_restore -U lmi -d lmi --clean --if-exists < /ścieżka/radar.dump
# protokoły: baza i zdjęcia
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in protokoly-baza.dump.enc > protokoly.dump
cd /opt/protokoly && docker compose exec -T db pg_restore -U protokoly -d protokoly --clean --if-exists < /ścieżka/protokoly.dump
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in protokoly-zdjecia.tgz.enc | tar -C /opt -xz
# kartoteka (zatrzymaj kontener na czas podmiany pliku)
cd /opt/kartoteka && docker compose stop kartoteka
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in kartoteka-baza.tgz.enc | gunzip > /opt/kartoteka-dane/kartoteka.db
rm -f /opt/kartoteka-dane/kartoteka.db-wal /opt/kartoteka-dane/kartoteka.db-shm && docker compose start kartoteka
```
(Na nowym serwerze: hasło z menedżera haseł zapisz najpierw do `/opt/kopie/haslo`.)

## Ręczne uruchomienie i stan
`systemctl start pracawre-kopia` · `journalctl -u pracawre-kopia -n 20` · `systemctl list-timers pracawre-kopia.timer`
