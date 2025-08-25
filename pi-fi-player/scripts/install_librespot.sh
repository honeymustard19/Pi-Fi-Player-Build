#!/usr/bin/env bash
set -euo pipefail
mkdir -p ~/librespot-bin
cd ~/librespot-bin
echo "[*] Fetching latest librespot (armv7) ..."
curl -L https://github.com/librespot-org/librespot/releases/latest/download/librespot-armv7.zip -o librespot.zip
unzip -o librespot.zip
chmod +x librespot
echo "[*] Installed to ~/librespot-bin/librespot"
