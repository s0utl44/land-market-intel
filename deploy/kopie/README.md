# Kopia zapasowa pracawre.com na Dysk Google

Co noc o 02:40 `kopia.sh` wysyła na Dysk współdzielony Google trzy zaszyfrowane pliki (AES-256, hasło tylko na
serwerze i w menedżerze haseł): bazę radaru, dane generatora umów i pliki `.env`. Dzienne zostają 14 dni,
miesięczne (z 1. dnia miesiąca) około roku. Dysk widzi tylko zaszyfrowane pliki — bez hasła nie da się ich odczytać.

## Odtworzenie
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in umowy-dane.tgz.enc | tar -C /opt -xz
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:/opt/kopie/haslo -in radar-baza.dump.enc > radar.dump
cd /opt/lmi && docker compose exec -T db pg_restore -U lmi -d lmi --clean --if-exists < /ścieżka/radar.dump
```
(Na nowym serwerze: hasło z menedżera haseł zapisz najpierw do `/opt/kopie/haslo`.)

## Ręczne uruchomienie i stan
`systemctl start pracawre-kopia` · `journalctl -u pracawre-kopia -n 20` · `systemctl list-timers pracawre-kopia.timer`
