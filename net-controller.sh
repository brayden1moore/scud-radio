#!/bin/bash
# net-controller.sh — the single owner of all Wi-Fi connection decisions.
#
# Usage:
#   net-controller.sh boot    (run once at startup by net-controller.service)
#   net-controller.sh retry   (run by api.py after a user submits credentials)
#   net-controller.sh portal  (force setup portal; bench + "re-enter setup")
#
# Design: this is the ONLY thing that connects Wi-Fi. NM autoconnect is disabled
# PER-PROFILE (see disable_autoconnect below) so NM never races us by bringing a
# saved network up on its own at boot. Because we only ever call `connection up`
# on networks confirmed present in a completed scan, an out-of-range saved
# network is never attempted — so the 25s-per-network association walk is
# impossible. The single-network fast path bounds its one attempt with --wait.

set -u

IFACE="wlan0"
AP_CON="scud-ap"
AP_SSID="Scud House"          # constant across all units (branding)
AP_ADDR="192.168.4.1/24"
PORTAL_PORT="888"

# How long to wait for a wifi scan to actually produce results before deciding
# a saved network is "not in range". Must exceed a real scan (~3-4s observed).
SCAN_TIMEOUT=8
# Bound on a single association attempt (fast path + per-network in multi path).
ASSOC_WAIT=8

log() { echo "net-controller: $*"; }

# ---- kill NM autoconnect on every saved wifi profile (except our AP) --------
# This is the race fix. netplan- and portal-generated profiles ship with
# autoconnect=yes; if we don't disable it, NM brings them up in parallel with
# us at boot and whoever wins is nondeterministic. Run this BEFORE we make any
# connection decision. Idempotent; safe to run every boot.
disable_autoconnect() {
  local uuid name
  while IFS=: read -r uuid name; do
    [ -z "$uuid" ] && continue
    [ "$name" = "$AP_CON" ] && continue
    nmcli connection modify uuid "$uuid" connection.autoconnect no 2>/dev/null || true
  done < <(nmcli -t -f UUID,NAME,TYPE connection show \
             | awk -F: '$3=="802-11-wireless"{print $1":"$2}')
}

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

# ---- wait for a completed scan, return the list of visible SSIDs -----------
# Triggers a rescan, then polls until wifi list is non-empty or SCAN_TIMEOUT.
# Prints visible SSIDs (one per line). Empty output => scan genuinely found
# nothing (not just "we asked too early"), because we waited for completion.
scan_visible() {
  local waited=0 visible=""
  # Ask for a fresh scan. If NM says a scan is already in progress that's fine.
  nmcli device wifi rescan ifname "$IFACE" 2>/dev/null || true
  while [ "$waited" -lt "$SCAN_TIMEOUT" ]; do
    visible="$(nmcli -t -f SSID device wifi list ifname "$IFACE" 2>/dev/null | sed '/^$/d')"
    if [ -n "$visible" ]; then
      printf '%s\n' "$visible"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1   # timed out with no visible networks
}

# ---- connect to the strongest IN-RANGE known network ----
connect_known() {
  # Saved Wi-Fi profiles, excluding our own AP.
  mapfile -t saved < <(nmcli -t -f NAME,TYPE connection show \
    | awk -F: '$2=="802-11-wireless"{print $1}' \
    | grep -vx "$AP_CON")

  [ ${#saved[@]} -eq 0 ] && return 1

  # FAST PATH: exactly one saved network — try to bring it up directly.
  # Autoconnect is already off (disable_autoconnect ran), so NM is NOT racing
  # us for this profile; whichever of us activates it, it's us. --wait bounds
  # an out-of-range attempt so we fail in ~ASSOC_WAIT and fall to AP instead
  # of hanging. An in-range one connects in 2-4s.
  if [ ${#saved[@]} -eq 1 ]; then
    if nmcli --wait "$ASSOC_WAIT" connection up id "${saved[0]}" 2>/dev/null; then
      return 0
    fi
    return 1
  fi

  # MULTI-NETWORK PATH: wait for a COMPLETED scan, then walk visible networks
  # strongest-first and connect to the first that's saved. We only attempt
  # networks confirmed visible, so no out-of-range association walk.
  local visible
  visible="$(scan_visible)" || return 1   # no networks visible after full scan

  # Walk saved profiles ordered by the scan's signal strength.
  while IFS=: read -r signal ssid; do
    [ -z "$ssid" ] && continue
    for s in "${saved[@]}"; do
      if [ "$s" = "$ssid" ]; then
        if nmcli --wait "$ASSOC_WAIT" connection up id "$s" 2>/dev/null; then
          return 0
        fi
      fi
    done
  done < <(nmcli -t -f SIGNAL,SSID device wifi list ifname "$IFACE" 2>/dev/null \
             | sed '/^$/d' | sort -rn -t: -k1)

  return 1
}

start_radio() {
  systemctl stop launcher.service 2>/dev/null || true
  systemctl start radio.service
}

# ---- main ----
case "${1:-boot}" in
  boot)
    disable_autoconnect          # <-- must run before any connection decision
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
    disable_autoconnect          # new profile may have shipped autoconnect=yes
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
    log "forcing setup portal"
    systemctl stop radio.service 2>/dev/null || true
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