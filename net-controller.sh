#!/bin/bash
# net-controller.sh — the single owner of all Wi-Fi connection decisions.
#
# Usage:
#   net-controller.sh boot    (run once at startup by net-controller.service)
#   net-controller.sh retry   (run by api.py after a user submits credentials)
#
# Design: this is the ONLY thing that connects Wi-Fi. NM autoconnect is disabled
# globally, and comitup is not installed. Because we only ever call `connection up`
# on networks confirmed present in a fresh scan, an out-of-range saved network is
# never attempted — so the 25s-per-network association-timeout walk is impossible.

set -u

IFACE="wlan0"
AP_CON="scud-ap"
AP_SSID="Scud House"          # constant across all units (branding)
AP_ADDR="192.168.4.1/24"
PORTAL_PORT="888"

log() { echo "net-controller: $*"; }

# ---- iptables captive redirect (scoped to the AP interface only) ----
redirect_up() {
  iptables -t nat -C PREROUTING -i "$IFACE" -p tcp --dport 80 -j REDIRECT --to-ports "$PORTAL_PORT" 2>/dev/null \
    || iptables -t nat -A PREROUTING -i "$IFACE" -p tcp --dport 80 -j REDIRECT --to-ports "$PORTAL_PORT"
}

# ---- AP lifecycle ----
ap_up() {
  # Create the AP profile if it doesn't exist yet (idempotent).
  if ! nmcli -t -f NAME connection show | grep -qx "$AP_CON"; then
    nmcli connection add type wifi ifname "$IFACE" con-name "$AP_CON" \
      autoconnect no ssid "$AP_SSID" \
      802-11-wireless.mode ap 802-11-wireless.band bg \
      ipv4.method shared ipv4.addresses "$AP_ADDR"
  fi
  nmcli connection up "$AP_CON"
  redirect_up
  systemctl start launcher.service    # Welcome screen with join instructions
}

ap_down() {
  nmcli connection down "$AP_CON" 2>/dev/null || true
}

# ---- connect to the strongest IN-RANGE known network ----
connect_known() {
  nmcli device wifi rescan 2>/dev/null || true

  # Wait briefly for scan results to populate.
  local visible="" i
  for i in 1 2 3; do
    visible="$(nmcli -t -f SSID device wifi list 2>/dev/null | sed '/^$/d')"
    [ -n "$visible" ] && break
    sleep 1
  done

  # Saved Wi-Fi profiles, excluding our own AP.
  mapfile -t saved < <(nmcli -t -f NAME,TYPE connection show \
    | awk -F: '$2=="802-11-wireless"{print $1}' \
    | grep -vx "$AP_CON")

  [ ${#saved[@]} -eq 0 ] && return 1

  # Walk visible networks strongest-first; connect to the first that is also saved.
  # We only ever try networks that appeared in the scan, so no timeout on absent ones.
  while IFS=: read -r signal ssid; do
    for s in "${saved[@]}"; do
      if [ "$s" = "$ssid" ]; then
        if nmcli --wait 12 connection up id "$s" 2>/dev/null; then
          nmcli connection modify "$s" connection.autoconnect no 2>/dev/null || true
          return 0
        fi
      fi
    done
  done < <(nmcli -t -f SIGNAL,SSID device wifi list 2>/dev/null | sed '/^$/d' | sort -rn -t: -k1)

  return 1
}

start_radio() {
  systemctl stop launcher.service 2>/dev/null || true
  systemctl start radio.service
}

# ---- main ----
case "${1:-boot}" in
  boot)
    if connect_known; then
      log "connected to known network"
      ap_down
      start_radio
    else
      log "no known network in range — raising AP"
      ap_up
    fi
    ;;
  retry)
    # Called after the user submits credentials via the captive portal.
    if connect_known; then
      log "connected after credential entry"
      ap_down
      start_radio
    else
      log "credential attempt failed — staying in AP mode"
      ap_up
    fi
    ;;
  portal)
    # Force the setup portal regardless of known networks.
    # Use for bench testing, and as a "re-enter setup" path on shipped units
    # (e.g. a long-press button or a /reset-wifi API route can call this).
    log "forcing setup portal"
    # If the radio is currently playing, stop it so the Welcome screen shows.
    systemctl stop radio.service 2>/dev/null || true
    # Drop any active client connection so the AP owns the radio.
    active="$(nmcli -t -f NAME,TYPE connection show --active \
              | awk -F: '$2=="802-11-wireless"{print $1}' | grep -vx "$AP_CON")"
    if [ -n "$active" ]; then
      while IFS= read -r c; do
        [ -n "$c" ] && nmcli connection down "$c" 2>/dev/null || true
      done <<< "$active"
    fi
    ap_up
    ;;
  *)
    log "unknown mode: ${1:-}" ; exit 1 ;;
esac

exit 0