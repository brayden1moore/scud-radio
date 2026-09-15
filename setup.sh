#!/bin/bash
# setup.sh [unit-suffix] [--dac pcm5100a|wm8960]
#
# Run once when preparing a unit to ship. Optional suffix sets the unit's
# unique hostname:  ./setup.sh 3a4b  ->  radio-3a4b.local
# With no arg, the suffix defaults to the last 4 of the Pi's serial, so every
# unit still gets a unique hostname with zero tracking. Pass an arg to override
# with a friendlier name, e.g. ./setup.sh kitchen -> radio-kitchen.local
#
# --dac selects the audio hardware. Default is pcm5100a (hifiberry-dac overlay,
# mainline kernel driver, no vendor install). Pass --dac wm8960 for the old
# Waveshare HAT, which needs the vendor driver build.
#   ./setup.sh kitchen --dac wm8960

set -e

# ---------- args ----------
SUFFIX=""
DAC="pcm5100a"

while [ $# -gt 0 ]; do
  case "$1" in
    --dac)   DAC="$2"; shift 2 ;;
    --dac=*) DAC="${1#*=}"; shift ;;
    -h|--help)
      echo "usage: $0 [unit-suffix] [--dac pcm5100a|wm8960]"
      exit 0 ;;
    -*)
      echo "unknown option: $1" >&2; exit 1 ;;
    *)
      SUFFIX="$1"; shift ;;
  esac
done

case "$DAC" in
  pcm5100a|pcm5102a|hifiberry|hifiberry-dac) DAC="pcm5100a" ;;
  wm8960|waveshare)                          DAC="wm8960"   ;;
  *) echo "unknown --dac '$DAC' (expected pcm5100a or wm8960)" >&2; exit 1 ;;
esac

if [ "$DAC" = "wm8960" ]; then
  DAC_OVERLAY="dtoverlay=wm8960-soundcard"
  ALSA_CARD="wm8960soundcard"
else
  DAC_OVERLAY="dtoverlay=hifiberry-dac"
  ALSA_CARD="sndrpihifiberry"
fi

# ---------- unit identity ----------
if [ -z "$SUFFIX" ]; then
  SUFFIX="$(grep -m1 Serial /proc/cpuinfo | awk '{print $3}' | tail -c 5)"
fi
HOSTNAME="radio-${SUFFIX}"
echo "Preparing unit: hostname will be ${HOSTNAME}.local"
echo "Audio: ${DAC} (${DAC_OVERLAY})"

# ---------- boot config ----------
sudo rm -f /boot/firmware/config.txt
sudo tee /boot/firmware/config.txt > /dev/null <<EOF
auto_initramfs=0
${DAC_OVERLAY}
enable_uart=1
dtoverlay=disable-bt
disable_splash=1

initial_turbo=20
dtparam=i2c_arm=on
dtparam=spi=on
camera_auto_detect=0
display_auto_detect=0
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
dtoverlay=disable-eth
arm_boost=1

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
EOF

# ---------- bootloader: eMMC only, DISABLE_HDMI, force fast firmware boot ----------
# On CM4, rpi-eeprom-config is disabled by default. Enable the flashrom path first.
echo 'RPI_EEPROM_USE_FLASHROM=1' | sudo tee -a /etc/default/rpi-eeprom-update
echo 'CM4_ENABLE_RPI_EEPROM_UPDATE=1' | sudo tee -a /etc/default/rpi-eeprom-update

# Read current EEPROM config, modify it, apply. (Read-modify-write, not a hand-authored file.)
rpi-eeprom-config > /tmp/boot.conf
sed -i 's/^BOOT_ORDER=.*/BOOT_ORDER=0xf1/' /tmp/boot.conf
sed -i 's/^DISABLE_HDMI=.*/DISABLE_HDMI=1/' /tmp/boot.conf
# if the keys don't already exist in the dumped config, append them
grep -q '^BOOT_ORDER='  /tmp/boot.conf || echo 'BOOT_ORDER=0xf1'  >> /tmp/boot.conf
grep -q '^DISABLE_HDMI=' /tmp/boot.conf || echo 'DISABLE_HDMI=1' >> /tmp/boot.conf

# Apply — and DON'T swallow the error, so a failed flash is visible during prep.
sudo rpi-eeprom-config --apply /tmp/boot.conf

# ---------- audio ----------
if [ "$DAC" = "wm8960" ]; then
  # WM8960 (overlay baked in; disable slow Waveshare service)
  cd ~/
  if [ ! -d WM8960-Audio-HAT ]; then
    git clone https://github.com/waveshare/WM8960-Audio-HAT
  fi
  cd WM8960-Audio-HAT
  sudo chmod +x install.sh
  sudo ./install.sh -y
  cd ~/
  sudo ln -sf /etc/wm8960-soundcard/asound.conf /etc/asound.conf
  sudo ln -sf /etc/wm8960-soundcard/wm8960_asound.state /var/lib/alsa/asound.state
  sudo systemctl disable wm8960-soundcard.service
  # WM8960 has a real hardware mixer that comes up attenuated; open it all the
  # way so mpv's software volume is the only thing in the path.
  sudo apt install mpv -y
  amixer -D pulse sset Master 100% || amixer sset Master 100% || true
else
  # PCM5100A via hifiberry-dac: driver is in the mainline kernel, nothing to
  # build. The chip has no I2C control port, so ALSA exposes no mixer controls
  # at all — that's expected, not a fault. mpv does volume in software.
  # Point "default" at the card by name rather than relying on card 0 ordering.
  sudo rm -f /etc/asound.conf
  sudo tee /etc/asound.conf > /dev/null <<EOF
pcm.!default {
    type plug
    slave.pcm "hw:CARD=${ALSA_CARD},DEV=0"
}

ctl.!default {
    type hw
    card "${ALSA_CARD}"
}
EOF
  # Nothing to save or restore at boot on this card; drop any stale wm8960 link.
  sudo rm -f /var/lib/alsa/asound.state
  sudo apt install mpv -y
fi

# ---------- hostname (unique per unit, for radio-<suffix>.local) ----------
sudo hostnamectl set-hostname "$HOSTNAME"
if grep -q '^127.0.1.1' /etc/hosts; then
  sudo sed -i "s/^127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts
else
  echo -e "127.0.1.1\t${HOSTNAME}" | sudo tee -a /etc/hosts > /dev/null
fi

# ---------- network controller service (replaces wifi-connect + comitup) ----------
sudo chmod 600 /lib/netplan/*.yaml 2>/dev/null || true
chmod +x /home/scud/scud-radio/net-controller.sh
sudo tee /etc/systemd/system/net-controller.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Network Controller
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/home/scud/scud-radio/net-controller.sh boot
SuccessExitStatus=0 1

[Install]
WantedBy=multi-user.target
EOF

# ---------- splash service ----------
sudo tee /etc/systemd/system/splash.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Splash Screen
DefaultDependencies=no
After=local-fs.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 -u /home/scud/scud-radio/splash.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=sysinit.target
EOF

# ---------- launcher service (Welcome screen) ----------
sudo tee /etc/systemd/system/launcher.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Tuner Launcher
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/launcher.py
ExecStartPre=/bin/systemctl stop radio.service
ExecStartPre=/bin/systemctl stop splash.service
Restart=no

[Install]
WantedBy=multi-user.target
EOF

# ---------- radio service ----------
sudo tee /etc/systemd/system/radio.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Tuner
After=api.service
Conflicts=splash.service launcher.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStartPre=/bin/systemctl start api.service
ExecStartPre=/bin/systemctl stop launcher.service
ExecStartPre=/bin/systemctl stop splash.service
ExecStart=/usr/bin/python3 /home/scud/scud-radio/radio.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
EOF

# ---------- shutdown service ----------
sudo tee /etc/systemd/system/shutdown.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Tuner Shutdown
Conflicts=radio.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/shutdown.py
ExecStartPre=/bin/systemctl stop radio.service

[Install]
WantedBy=multi-user.target
EOF

# ---------- api service ----------
sudo tee /etc/systemd/system/api.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Tuner API
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/scud/scud-radio/api.py
WorkingDirectory=/home/scud/scud-radio
User=root
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# ---------- NetworkManager: never autoconnect (controller owns connections) ----------
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/no-autoconnect.conf > /dev/null <<EOF
[connection]
connection.autoconnect=false
EOF

sudo rm -f /etc/NetworkManager/NetworkManager.conf
sudo tee /etc/NetworkManager/NetworkManager.conf > /dev/null <<EOF
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=false

[connectivity]
enabled=false
EOF

# ---------- captive-portal DNS hijack (AP / shared mode only) ----------
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
sudo tee /etc/NetworkManager/dnsmasq-shared.d/captive.conf > /dev/null <<EOF
address=/#/192.168.4.1
EOF

# ---------- enable services ----------
sudo systemctl daemon-reload
sudo systemctl enable splash
sudo systemctl enable net-controller
sudo systemctl enable api

# ---------- dependencies ----------
sudo apt install pip -y
cd /home/scud/scud-radio
sudo -H pip install --break-system-packages Flask
sudo -H pip install --break-system-packages -r requirements.txt

# ---------- networking tools ----------
sudo apt install iptables -y

# ---------- trims (unchanged from before) ----------
sudo apt update
sudo systemctl disable man-db.service || true
sudo systemctl disable e2scrub_reap.service || true
sudo systemctl disable ModemManager.service || true
sudo systemctl disable NetworkManager-wait-online.service || true
sudo systemctl disable apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer || true
# cloud-init: disable fully if present
sudo touch /etc/cloud/cloud-init.disabled 2>/dev/null || true
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

echo "Setup complete for ${HOSTNAME} (${DAC}). Rebooting..."
sudo reboot