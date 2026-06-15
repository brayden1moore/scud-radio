#!/bin/bash

# This script is called by comitup when connection state changes
# Arguments: $1 = state (HOTSPOT, CONNECTING, CONNECTED)

case "$1" in
    CONNECTED)
        active=$(nmcli -t -f NAME,TYPE connection show --active | awk -F: '$2=="802-11-wireless"{print $1}' | head -1)
        [ -n "$active" ] && sudo nmcli connection modify "$active" connection.autoconnect no
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