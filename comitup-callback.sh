#!/bin/bash

# This script is called by comitup when connection state changes
# Arguments: $1 = state (HOTSPOT, CONNECTING, CONNECTED)

case "$1" in
    CONNECTED)
        # Disable autoconnect on ALL saved wifi profiles, not just the active one
        nmcli -t -f NAME,TYPE connection show \
        | awk -F: '$2=="802-11-wireless"{print $1}' \
        | grep -v -E '^comitup-' \
        | while read -r name; do
            sudo nmcli connection modify "$name" connection.autoconnect no
            done
        sudo /bin/systemctl stop launcher.service
        sudo /bin/systemctl stop splash.service
        sudo /bin/systemctl start radio.service
        ;;
    CONNECTING)
        # add connecting screen
        ;;
    HOTSPOT)
        sudo /bin/systemctl stop radio.service
        sudo /bin/systemctl start launcher.service
        ;;
esac