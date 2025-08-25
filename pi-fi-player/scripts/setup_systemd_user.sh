#!/usr/bin/env bash
set -euo pipefail
mkdir -p ~/.config/systemd/user
cp "$(pwd)/services/librespot.service" ~/.config/systemd/user/librespot.service
cp "$(pwd)/services/pifi.service" ~/.config/systemd/user/pifi.service
systemctl --user daemon-reload
systemctl --user enable --now librespot.service
systemctl --user enable --now pifi.service
sudo loginctl enable-linger $USER
echo "[*] Services enabled. Reboot to test autostart."
