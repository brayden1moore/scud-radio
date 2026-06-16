#!/bin/bash

# Initial setup
sudo rm /boot/firmware/config.txt
sudo tee /boot/firmware/config.txt > /dev/null <<EOF
dtoverlay=hifiberry-dac
dtoverlay=disable-bt
disable_splash=1

dtparam=i2c_arm=on
#dtparam=i2s=on
dtparam=spi=on
#dtparam=audio=on
camera_auto_detect=1
display_auto_detect=0
auto_initramfs=1
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
EOF

cd ~/
git clone https://github.com/waveshare/WM8960-Audio-HAT
cd WM8960-Audio-HAT
sudo chmod +x install.sh
sudo ./install.sh -y
cd ~/

sudo apt install mpv -y
amixer -D pulse sset Master 100%

# Create wifi connect service file
sudo tee /etc/systemd/system/wifi-connect.service > /dev/null <<EOF

[Unit]
Description=Scan-first WiFi connect
After=NetworkManager.service
Wants=NetworkManager.service
Before=comitup.service

[Service]
Type=oneshot
ExecStart=/home/scud/scud-radio/wifi-connect.sh
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
EOF
chmod +x /home/scud/scud-radio/wifi-connect.sh

# Create the splash service file
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

# Create the launcher service file
sudo tee /etc/systemd/system/launcher.service > /dev/null <<EOF
[Unit]
Description=Scud Radio Tuner Launcher
After=NetworkManager.service
Wants=NetworkManager.service
Before=network-online.target
After=comitup.service

[Service]
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/launcher.py
ExecStartPre=/bin/bash -c 'while sudo iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 888 2>/dev/null; do :; done'
ExecStartPre=/bin/systemctl stop radio.service
ExecStartPre=/bin/systemctl stop splash.service
ExecStartPre=/bin/systemctl stop api.service
Restart=no

[Install]
WantedBy=multi-user.target
EOF

# Create the radio service file
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

# Create the shutdown service file
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

# Create the api service file
sudo tee /etc/systemd/system/api.service > /dev/null <<EOF

[Unit] 
Description=Scud Radio Tuner API 
After=network.target 

[Service] 
ExecStart=/usr/bin/python3 /home/scud/scud-radio/api.py 
#ExecStart=/usr/bin/python3 -m gunicorn --worker-class eventlet --workers 1 --timeout 0 --bind 127.0.0.1:7777 api:app
ExecStartPre=/usr/bin/sudo /usr/sbin/iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 888
WorkingDirectory=/home/scud/scud-radio 
User=root 
Restart=always 

[Install] 
WantedBy=multi-user.target
EOF

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable splash
sudo systemctl enable wifi-connect

# Install dependencies
sudo apt install pip -y
sudo -H  pip install gunicorn eventlet Flask --break-system-packages
cd scud-radio
sudo -H pip install --break-system-packages -r requirements.txt

# Networking
sudo apt install iptables -y

# Other settings
sudo apt update
sudo apt install comitup -y --fix-missing
sudo apt install --fix-broken
sudo systemctl enable comitup
sudo systemctl disable man-db.service
sudo systemctl disable e2scrub_reap.service
sudo systemctl disable ModemManager.service
sudo systemctl disable cloud-init-main.service
sudo systemctl disable NetworkManager-wait-online.service
sudo systemctl disable apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Copy comitup templates
sudo cp -a ~/scud-radio/comitup-templates/. /usr/share/comitup/web/templates/

# add Comitup config
sudo rm -f /etc/comitup.conf
sudo tee /etc/comitup.conf > /dev/null <<EOF
ap_name: Scud House
web_service: radio.service
external_callback: /home/scud/scud-radio/comitup-callback.sh
EOF
chmod +x /home/scud/scud-radio/comitup-callback.sh

# add NM config
sudo rm -f /etc/NetworkManager/NetworkManager.conf
sudo tee /etc/NetworkManager/NetworkManager.conf > /dev/null <<EOF
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=false

[connectivity]
uri=http://connectivity-check.ubuntu.com/
interval=300
enabled=false
EOF

if ! grep -q 'subprocess.run(\["sudo","systemctl","start","launcher"\])' /usr/share/comitup/web/comitupweb.py; then
    sudo sed -i '1i import subprocess\nsubprocess.run(["sudo","systemctl","start","launcher"])' /usr/share/comitup/web/comitupweb.py
fi


sudo reboot