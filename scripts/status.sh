#!/usr/bin/env bash
# Stan wszystkich pobierań na serwerze: co działa teraz, ostatnie linie logów, przebiegi w bazie, postęp RCN.
# Użycie: cd /opt/lmi && bash scripts/status.sh
cd "$(dirname "$0")/.." || exit 1
psql() { docker compose exec -T db psql -U lmi -d lmi -P pager=off "$@"; }

echo "=== Działa teraz"
docker ps --filter name=lmi-app-run --format '{{.ID}} {{.Status}}' | while read -r id status; do
  echo "  $(docker inspect -f '{{.Args}}' "$id" | tr -d '[]') · $status"
done
[ -z "$(docker ps -q --filter name=lmi-app-run)" ] && echo "  nic (żadne pobieranie nie trwa)"

echo
echo "=== Zadania (systemd)"
for u in lmi-daily lmi-daily-retry lmi-rcn-init lmi-nonline-init lmi-adresowo-init lmi-gratka-init lmi-otodom-now; do
  state=$(systemctl show -p ActiveState --value "$u" 2>/dev/null)
  [ -z "$state" ] || [ "$state" = "inactive" ] && [ -z "$(journalctl -u "$u" --since today -q --no-pager 2>/dev/null | head -1)" ] && continue
  result=$(systemctl show -p Result --value "$u" 2>/dev/null)
  last=$(journalctl -u "$u" --since today --no-pager -q 2>/dev/null \
         | grep -E "INFO|BŁĄD|BLOKADA|Incomplete|Error|import|zapisano|Deduplikacja|stron|pobrano" | tail -1 | cut -c1-170)
  printf "  %-20s %-9s %-9s %s\n" "$u" "$state" "$result" "${last#* * * }"
done

echo
echo "=== Ostatnie przebiegi portali"
psql -c "SELECT run_id, source_id, finished_at::timestamp(0) AS koniec, status, rows_written AS wiersze,
                left(coalesce(message, ''), 70) AS uwagi
         FROM scrape.runs ORDER BY run_id DESC LIMIT 8"

echo "=== Oferty w pamięci podręcznej (pobrane strony ofert)"
psql -c "SELECT 'otodom' AS portal, count(*) AS oferty, max(fetched_at)::timestamp(0) AS ostatnia FROM scrape.otodom_details
         UNION ALL SELECT source_id, count(*), max(fetched_at)::timestamp(0) FROM scrape.portal_details GROUP BY 1 ORDER BY 1"

echo "=== RCN (ceny transakcyjne)"
psql -c "SELECT count(*) AS rekordy_dzialek, min(doc_date) AS od, max(doc_date) AS do_dnia,
                (SELECT count(*) FROM mart.rcn_land_transactions) AS transakcje_gruntowe
         FROM scrape.rcn_parcels" 2>/dev/null
psql -c "SELECT fetched_at::timestamp(0) AS kiedy, coalesce(period_start::text, 'bez daty') AS okres,
                matched AS w_usludze, saved AS zapisane
         FROM scrape.rcn_fetch_log ORDER BY fetched_at DESC LIMIT 5" 2>/dev/null
