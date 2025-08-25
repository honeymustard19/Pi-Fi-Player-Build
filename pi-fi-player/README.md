# Pi‑Fi Player

Portable, distraction‑free **Spotify Connect** player for Raspberry Pi with a touch UI built in **Kivy**.
Boots straight into the app and plays to a high‑fidelity DAC HAT or USB DAC.

> **Note:** Spotify offline downloads are not supported via public APIs. This project is a streaming endpoint.

## Features
- Kivy touch UI: **Play/Pause/Next/Prev**, Now Playing, playlists list
- Spotify auth via **Authorization Code + PKCE** (QR/URL shown on the device)
- Works with **librespot** for high‑quality Spotify Connect playback (OGG → ALSA → DAC)
- Optional **GPIO** rotary encoder (volume) + buttons
- **Boot‑to‑app** with systemd user services

## Hardware (suggested)
- Raspberry Pi 4B (2–4 GB), passive heatsinks
- DAC HAT (HiFiBerry DAC+ Pro / IQaudIO Pi‑DAC+) or USB DAC (DragonFly, FiiO E10K)
- 4–5" DSI touchscreen (preferred)
- Battery + power‑management HAT (PiJuice / UPS HAT) for portable use
- High‑endurance A2 microSD (128–256 GB)

## Quick start
```bash
# On the Pi
git clone https://github.com/<your-username>/pi-fi-player.git
cd pi-fi-player

# Install librespot (Spotify Connect endpoint)
chmod +x scripts/install_librespot.sh
./scripts/install_librespot.sh

# Python env
python3 -m venv venv
source venv/bin/activate
pip install -r pi-fi/requirements.txt

# Config
cp pi-fi/settings.example.toml pi-fi/settings.toml
cp .env.example .env
# Edit pi-fi/settings.toml for device_name/redirect_uri if you prefer TOML,
# OR set environment variables in .env (see below).

# First run (to authorize, shows a QR/URL)
cd pi-fi
python3 main.py

# Enable services to boot straight into the player
cd ..
chmod +x scripts/setup_systemd_user.sh
./scripts/setup_systemd_user.sh
```

## Spotify App Setup
Create an app at <https://developer.spotify.com/dashboard> and add redirect URIs:
- `http://pi.local:8080/callback`
- `http://<PI_IP>:8080/callback`

## Configuration
Two ways to provide settings (both are supported):

**A) Environment variables (.env)**  
Create a `.env` (or copy `.env.example`):
```
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_REDIRECT_URI=http://pi.local:8080/callback
SPOTIFY_SCOPES=user-read-playback-state,user-modify-playback-state,playlist-read-private,playlist-read-collaborative,user-read-currently-playing
DEVICE_NAME=Pi-Fi Player
VOLUME_STEP=5
```

**B) TOML file**  
`pi-fi/settings.example.toml` → copy to `pi-fi/settings.toml` and fill the same values.

Env vars take precedence over TOML.

## Systemd Services
- `services/librespot.service` — runs librespot on boot
- `services/pifi.service` — runs the Kivy UI on boot

Edit DAC ALSA device with `aplay -l` and update `--device` in `librespot.service` if needed.

## Development
```bash
make lint
```
PRs run flake8 via GitHub Actions.

## License
MIT
