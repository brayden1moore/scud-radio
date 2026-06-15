#!/bin/bash
# Scan for visible APs, connect only to a SAVED network that's actually in range.
# If none visible, exit nonzero so comitup handles hotspot/onboarding.
set -u

# Trigger a rescan and give the supplicant time to populate results
nmcli device wifi rescan 2>/dev/null || true
for i in 1 2 3 4 5; do
  visible="$(nmcli -t -f SSID device wifi list 2>/dev/null | sed '/^$/d' | sort -u)"
  [ -n "$visible" ] && break
  sleep 1
done

# Saved wifi connection profiles (exclude the comitup hotspot + One-Radio AP)
mapfile -t saved < <(nmcli -t -f NAME,TYPE connection show \
  | awk -F: '$2=="802-11-wireless"{print $1}' \
  | grep -v -E '^(comitup-|One-Radio)')

# Try visible saved networks, strongest signal first
while IFS=: read -r signal ssid; do
  for s in "${saved[@]}"; do
    if [ "$s" = "$ssid" ]; then
      if nmcli connection up id "$s" 2>/dev/null; then
        exit 0
      fi
    fi
  done
done < <(nmcli -t -f SIGNAL,SSID device wifi list 2>/dev/null | sed '/^$/d' | sort -rn -t: -k1)

# Nothing saved is in range → let comitup do its thing
exit 1