#!/bin/bash
# tools/install_airplay.sh [--dac pcm5100a|wm8960]
#
# Adds AirPlay to Otis: builds shairport-sync (AirPlay 2) + nqptp, writes
# their config and services, and (on the PCM5100A board) rewrites
# /etc/asound.conf so the radio and AirPlay share the DAC.
#
# setup.sh runs this during unit prep. To add AirPlay to a unit that's
# already set up:
#   cd ~/scud-radio && git pull && bash tools/install_airplay.sh && sudo reboot
#
# Shows up on phones and Macs as "Otis". radio.py reads the metadata pipe for
# play start/stop, track info and cover art, and steps the radio aside.

set -e

DAC="pcm5100a"
while [ $# -gt 0 ]; do
  case "$1" in
    --dac)   DAC="$2"; shift 2 ;;
    --dac=*) DAC="${1#*=}"; shift ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done
case "$DAC" in
  pcm5100a|pcm5102a|hifiberry|hifiberry-dac) DAC="pcm5100a" ;;
  wm8960|waveshare)                          DAC="wm8960"   ;;
  *) echo "unknown --dac '$DAC'" >&2; exit 1 ;;
esac

sudo apt update

# ---------- shared audio device ----------
if [ "$DAC" = "pcm5100a" ]; then
ALSA_CARD="sndrpihifiberry"
AIRPLAY_DEVICE="airplay"     # soft-volume in front of the shared dmix
# Radio (mpv) and AirPlay (shairport-sync) share the DAC through dmix, so
# neither can lock the other out. AirPlay gets its own device with a soft
# volume control ("AirPlay") that the volume knob drives; the radio keeps
# doing its volume inside mpv. dmix runs at 48 kHz to match mpv; AirPlay's
# 44.1 kHz is resampled with speex (libasound2-plugins).
sudo apt install libasound2-plugins -y
sudo rm -f /etc/asound.conf
sudo tee /etc/asound.conf > /dev/null <<EOF
defaults.pcm.rate_converter "speexrate_medium"

pcm.dmixer {
  type dmix
  ipc_key 1024
  ipc_perm 0666
  slave {
      pcm "hw:CARD=${ALSA_CARD},DEV=0"
      rate 48000
      format S32_LE
      channels 2
      period_size 1024
      buffer_size 8192
  }
}

pcm.!default {
  type plug
  slave.pcm "dmixer"
}

pcm.airplay_vol {
  type softvol
  slave.pcm "dmixer"
  control {
      name "AirPlay"
      card "${ALSA_CARD}"
  }
  min_dB -60.0
  max_dB 0.0
}

pcm.airplay {
  type plug
  slave.pcm "airplay_vol"
}

ctl.!default {
  type hw
  card "${ALSA_CARD}"
}
EOF
else
# WM8960 keeps its vendor asound.conf; AirPlay plays through "default" and
# the volume knob can't set an AirPlay level on this card.
AIRPLAY_DEVICE="default"
fi

# ---------- shairport-sync + nqptp ----------
# Shows up on phones and Macs as "Otis". radio.py reads the metadata pipe for
# play start/stop, track info and cover art, and steps the radio aside.
sudo apt install --no-install-recommends -y build-essential git autoconf automake libtool \
  libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev libssl-dev \
  libsoxr-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev libswresample-dev \
  uuid-dev libgcrypt20-dev xxd
sudo apt install --no-install-recommends -y libplist-dev || sudo apt install --no-install-recommends -y libplist-2.0-dev
sudo systemctl enable avahi-daemon

AIRPLAY_SRC=/home/scud/airplay-src
mkdir -p "$AIRPLAY_SRC"

# nqptp: the timing companion AirPlay 2 needs
cd "$AIRPLAY_SRC"
[ -d nqptp ] || git clone --depth 1 https://github.com/mikebrady/nqptp.git
cd nqptp
autoreconf -fi
./configure
make -j4
sudo make install

# shairport-sync
cd "$AIRPLAY_SRC"
[ -d shairport-sync ] || git clone --depth 1 https://github.com/mikebrady/shairport-sync.git
cd shairport-sync
autoreconf -fi
./configure --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl \
  --with-airplay-2 --with-metadata
make -j4
sudo make install

sudo tee /etc/shairport-sync.conf > /dev/null <<EOF
general = {
    name = "Otis";
    output_backend = "alsa";
    interpolation = "auto";
};

sessioncontrol = {
    allow_session_interruption = "yes";   // another phone can take over
    session_timeout = 20;
};

alsa = {
    output_device = "${AIRPLAY_DEVICE}";
};

metadata = {
    enabled = "yes";
    include_cover_art = "yes";
    pipe_name = "/tmp/shairport-sync-metadata";
    pipe_timeout = 5000;
};
EOF

# Our own units (run as root, like the radio's other services), so we don't
# depend on how a given shairport-sync release installs its own.
sudo tee /etc/systemd/system/nqptp.service > /dev/null <<EOF
[Unit]
Description=NQPTP (AirPlay 2 timing)
After=network.target

[Service]
ExecStart=/usr/local/bin/nqptp
User=root
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/shairport-sync.service > /dev/null <<EOF
[Unit]
Description=Otis AirPlay receiver (shairport-sync)
Wants=avahi-daemon.service nqptp.service
After=network.target avahi-daemon.service nqptp.service sound.target

[Service]
ExecStart=/usr/local/bin/shairport-sync -c /etc/shairport-sync.conf --log-to-syslog
User=root
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable nqptp shairport-sync
cd /home/scud/scud-radio
