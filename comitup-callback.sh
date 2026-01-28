#!/bin/bash

# This script is called by comitup when connection state changes
# Arguments: $1 = state (HOTSPOT, CONNECTING, CONNECTED)

case "$1" in
    CONNECTED)
        echo "Connected to WiFi - radio.service will start automatically"
        # Optional: Update LCD display to show "connected"
        ;;
    HOTSPOT)
        echo "In hotspot mode - radio.service stopped"
        # Optional: Update LCD display to show "portal mode"
        sudo systemctl start launcher
        ;;
esac