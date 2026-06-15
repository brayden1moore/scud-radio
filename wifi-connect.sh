#!/bin/bash
set -u
nmcli device wifi rescan 2>/dev/null || true
for i in 1 2 3 4 5; do
  visible="$(nmcli -t -f SSID device wifi list 2>/dev/null | sed '/^$/d')"
  [ -n "$visible" ] && break
  sleep 0.2
done

mapfile -t saved < <(nmcli -t -f NAME,TYPE connection show \
  | awk -F: '$2=="802-11-wireless"{print $1}' \
  | grep -v -E '^(comitup-|One-Radio)')

if [ ${#saved[@]} -eq 0 ]; then exit 1; fi

while IFS=: read -r signal ssid; do
  for s in "${saved[@]}"; do
    if [ "$s" = "$ssid" ]; then
      if nmcli --wait 10 connection up id "$s" 2>/dev/null; then
        exit 0
      fi
    fi
  done
done < <(nmcli -t -f SIGNAL,SSID device wifi list 2>/dev/null | sed '/^$/d' | sort -rn -t: -k1)

exit 1