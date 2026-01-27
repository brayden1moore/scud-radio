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
display_auto_detect=1
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
dtoverlay=gpio-shutdown,gpio_pin=17,active_low=1,gpio_pull=up
EOF


sudo apt install mpv
amixer -D pulse sset Master 100%

# Create the splash service file
sudo tee /etc/systemd/system/splash.service > /dev/null <<EOF
[Unit]
Description=One-Radio Tuner Splash
DefaultDependencies=no
Before=sysinit.target shutdown.target
Conflicts=shutdown.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/splash.py

[Install]
WantedBy=sysinit.target
EOF

# Create the launcher service file
sudo tee /etc/systemd/system/launcher.service > /dev/null <<EOF
[Unit]
Description=One-Radio Tuner Launcher
After=local-fs.target

[Service]
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/launcher.py
ExecStartPre=/bin/systemctl stop radio.service
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Create the radio service file
sudo tee /etc/systemd/system/radio.service > /dev/null <<EOF
[Unit]
Description=One-Radio Tuner
After=multi-user.target
Conflicts=splash.service launcher.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/scud/scud-radio
ExecStart=/usr/bin/python3 /home/scud/scud-radio/radio.py

ExecStartPre=/bin/systemctl start api.service
ExecStartPre=/bin/systemctl stop shutdown.service
ExecStartPre=/bin/systemctl stop launcher.service
ExecStartPre=/bin/systemctl stop splash.service
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create the shutdown service file
sudo tee /etc/systemd/system/shutdown.service > /dev/null <<EOF

[Unit] 
Description=One-Radio Tuner Shutdown
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
Description=One-Radio Tuner API 
After=network.target 

[Service] 
ExecStart=/usr/bin/python3 /home/scud/scud-radio/api.py 
#ExecStart=/usr/bin/python3 -m gunicorn --worker-class eventlet --workers 1 --timeout 0 --bind 127.0.0.1:7777 api:app
WorkingDirectory=/home/scud/scud-radio 
User=root 
Restart=always 

[Install] 
WantedBy=multi-user.target
EOF

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable splash
sudo systemctl enable launcher
sudo systemctl enable api

# Install dependencies
sudo -H  pip install gunicorn eventlet --break-system-packages
sudo -H pip install --break-system-packages -r requirements.txt

# Install battery
wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
bash pisugar-power-manager.sh -c release
sudo apt install netcat-traditional

# Networking
sudo apt install iptables -y

# Other settings
sudo systemctl stop cups
sudo systemctl disable man-db.service
sudo systemctl disable e2scrub_reap.service
sudo systemctl disable ModemManager.service
sudo systemctl disable cloud-init-main.service
sudo systemctl disable NetworkManager-wait-online.service
sudo systemctl disable apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8888