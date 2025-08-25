import os, sys, io, time, threading, socket
from functools import partial

# Kivy UI
from kivy.app import App
from kivy.config import Config
Config.set('graphics', 'fullscreen', 'auto')
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage

# Auth / API
import json, requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Local callback
from flask import Flask
from waitress import serve

# QR
import qrcode

# dotenv (env > toml)
from dotenv import load_dotenv
load_dotenv()

# GPIO (optional)
try:
    import RPi.GPIO as GPIO
    HW = True
except Exception:
    HW = False

# Settings: env first, then TOML fallback
def load_settings():
    cfg = {}
    cfg['client_id'] = os.getenv('SPOTIFY_CLIENT_ID')
    cfg['redirect_uri'] = os.getenv('SPOTIFY_REDIRECT_URI')
    cfg['scopes'] = os.getenv('SPOTIFY_SCOPES') or "user-read-playback-state,user-modify-playback-state,playlist-read-private,playlist-read-collaborative,user-read-currently-playing"
    cfg['device_name'] = os.getenv('DEVICE_NAME') or "Pi-Fi Player"
    cfg['volume_step'] = int(os.getenv('VOLUME_STEP') or 5)
    if not cfg['client_id'] or not cfg['redirect_uri']:
        try:
            import tomllib
            with open('settings.toml','rb') as f:
                t = tomllib.load(f)
                cfg['client_id'] = cfg['client_id'] or t.get('client_id')
                cfg['redirect_uri'] = cfg['redirect_uri'] or t.get('redirect_uri')
                cfg['scopes'] = os.getenv('SPOTIFY_SCOPES') or t.get('scopes', cfg['scopes'])
                cfg['device_name'] = os.getenv('DEVICE_NAME') or t.get('device_name', cfg['device_name'])
                cfg['volume_step'] = int(os.getenv('VOLUME_STEP') or t.get('volume_step', cfg['volume_step']))
        except Exception:
            pass
    return cfg

SETTINGS = load_settings()
CLIENT_ID    = SETTINGS['client_id']
REDIRECT_URI = SETTINGS['redirect_uri']
SCOPES       = SETTINGS['scopes']
DEVICE_NAME  = SETTINGS['device_name']
VOL_STEP     = SETTINGS['volume_step']

SPOTIFY = None
DEVICE_ID = None
app = None

# GPIO pins
PIN_ENC_A = 17
PIN_ENC_B = 27
PIN_ENC_SW = 22
PIN_BTN_PLAY = 5
PIN_BTN_NEXT = 6
PIN_BTN_PREV = 13

def setup_gpio():
    if not HW: return
    GPIO.setmode(GPIO.BCM)
    for p in [PIN_ENC_A, PIN_ENC_B, PIN_ENC_SW, PIN_BTN_PLAY, PIN_BTN_NEXT, PIN_BTN_PREV]:
        GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(PIN_ENC_A, GPIO.BOTH, callback=on_rotary)
    GPIO.add_event_detect(PIN_ENC_B, GPIO.BOTH, callback=on_rotary)
    GPIO.add_event_detect(PIN_ENC_SW, GPIO.FALLING, bouncetime=250, callback=lambda ch: toggle_play())
    GPIO.add_event_detect(PIN_BTN_PLAY, GPIO.FALLING, bouncetime=250, callback=lambda ch: toggle_play())
    GPIO.add_event_detect(PIN_BTN_NEXT, GPIO.FALLING, bouncetime=250, callback=lambda ch: cmd_next())
    GPIO.add_event_detect(PIN_BTN_PREV, GPIO.FALLING, bouncetime=250, callback=lambda ch: cmd_prev())

_last_enc = 0
def on_rotary(channel):
    if not HW: return
    global _last_enc
    a = GPIO.input(PIN_ENC_A)
    b = GPIO.input(PIN_ENC_B)
    val = (a << 1) | b
    if val == 0b01 and _last_enc == 0b00:
        volume_change(+VOL_STEP)
    elif val == 0b10 and _last_enc == 0b00:
        volume_change(-VOL_STEP)
    _last_enc = val

# Flask callback
flask_app = Flask(__name__)

@flask_app.route('/callback')
def callback():
    return "<html><body><h2>Pi‑Fi Player: Auth successful</h2>You may close this window.</body></html>"

def serve_flask():
    serve(flask_app, host='0.0.0.0', port=8080)

# UI
class PiFiUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.header = Label(text='Pi‑Fi Player', font_size='24sp', size_hint_y=None, height=48)
        self.add_widget(self.header)

        self.now = BoxLayout(orientation='horizontal', size_hint_y=None, height=200)
        self.art = Image(size_hint=(0.4,1))
        self.meta = BoxLayout(orientation='vertical')
        self.lbl_title = Label(text='—', halign='left', valign='middle')
        self.lbl_artist = Label(text='—', halign='left', valign='middle')
        self.progress = ProgressBar(max=100, value=0)
        self.meta.add_widget(self.lbl_title)
        self.meta.add_widget(self.lbl_artist)
        self.meta.add_widget(self.progress)
        self.now.add_widget(self.art)
        self.now.add_widget(self.meta)
        self.add_widget(self.now)

        tbar = BoxLayout(size_hint_y=None, height=70)
        self.btn_prev = Button(text='⏮')
        self.btn_play = Button(text='⏯')
        self.btn_next = Button(text='⏭')
        self.btn_prev.bind(on_release=lambda _: cmd_prev())
        self.btn_play.bind(on_release=lambda _: toggle_play())
        self.btn_next.bind(on_release=lambda _: cmd_next())
        tbar.add_widget(self.btn_prev)
        tbar.add_widget(self.btn_play)
        tbar.add_widget(self.btn_next)
        self.add_widget(tbar)

        self.play_scroller = ScrollView()
        self.play_grid = GridLayout(cols=1, size_hint_y=None, spacing=6, padding=[8,8])
        self.play_grid.bind(minimum_height=self.play_grid.setter('height'))
        self.play_scroller.add_widget(self.play_grid)
        self.add_widget(self.play_scroller)

        Clock.schedule_interval(lambda dt: refresh_state(), 1.0)

    def populate_playlists(self, playlists):
        self.play_grid.clear_widgets()
        for pl in playlists:
            btn = Button(text=pl['name'], size_hint_y=None, height=56, halign='left')
            btn.bind(on_release=lambda _btn, uri=pl['uri']: start_playlist(uri))
            self.play_grid.add_widget(btn)

    def show_auth_qr(self, url):
        qr = qrcode.QRCode(border=1, box_size=6)
        qr.add_data(url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
        self.art.texture = CoreImage(buf, ext='png').texture
        self.lbl_title.text = "Authorize Spotify"
        self.lbl_artist.text = f"Scan the QR or visit:\\n{url}"

def build_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=None,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_path=os.path.expanduser('~/.cache/pi_fi_spotipy'),
        open_browser=False,
        show_dialog=False
    ))

def ensure_device():
    global DEVICE_ID
    if SPOTIFY is None: return
    d = SPOTIFY.devices()
    dev = next((x for x in d.get('devices',[]) if x.get('name') == DEVICE_NAME), None)
    if dev:
        DEVICE_ID = dev['id']
    return DEVICE_ID

def transfer_to_device():
    if ensure_device():
        SPOTIFY.transfer_playback(device_id=DEVICE_ID, force_play=True)

def start_playlist(uri):
    transfer_to_device()
    SPOTIFY.start_playback(device_id=DEVICE_ID, context_uri=uri)

def toggle_play():
    if ensure_device():
        state = SPOTIFY.current_playback()
        if state and state.get('is_playing'):
            SPOTIFY.pause_playback(device_id=DEVICE_ID)
        else:
            SPOTIFY.start_playback(device_id=DEVICE_ID)

def cmd_next():
    if ensure_device():
        SPOTIFY.next_track(device_id=DEVICE_ID)

def cmd_prev():
    if ensure_device():
        SPOTIFY.previous_track(device_id=DEVICE_ID)

def volume_change(delta):
    if not ensure_device(): return
    state = SPOTIFY.current_playback()
    v = max(0, min(100, (state.get('device',{}).get('volume_percent',50) + delta)))
    SPOTIFY.volume(v, device_id=DEVICE_ID)

def refresh_state():
    if SPOTIFY is None: return
    state = SPOTIFY.current_playback()
    if not state: return
    item = state.get('item')
    if item:
        title = item.get('name','—')
        artists = ", ".join([a['name'] for a in item.get('artists',[])]) or '—'
        app.root.lbl_title.text = title
        app.root.lbl_artist.text = artists
        dur = item.get('duration_ms',1)
        pos = state.get('progress_ms',0)
        app.root.progress.max = dur
        app.root.progress.value = pos
        images = item.get('album',{}).get('images',[])
        if images:
            url = images[0]['url']
            try:
                r = requests.get(url, timeout=5)
                import io
                buf = io.BytesIO(r.content)
                app.root.art.texture = CoreImage(buf, ext='jpg').texture
            except Exception:
                pass

class PiFiApp(App):
    def build(self):
        self.title = "Pi‑Fi Player"
        return PiFiUI()

def oauth_or_show_qr(sp_oauth: SpotifyOAuth):
    auth_url = sp_oauth.get_authorize_url()
    print(f"[AUTH] Open on your phone: {auth_url}")
    app.root.show_auth_qr(auth_url)

def fetch_playlists():
    pls = []
    results = SPOTIFY.current_user_playlists(limit=50)
    while results:
        pls.extend(results['items'])
        if results['next']:
            results = SPOTIFY.next(results)
        else:
            break
    return [{'name': p['name'], 'uri': p['uri']} for p in pls]

def main():
    global SPOTIFY, app
    if not CLIENT_ID or not REDIRECT_URI:
        raise SystemExit("Missing SPOTIFY_CLIENT_ID or SPOTIFY_REDIRECT_URI (.env or settings.toml)")

    import threading
    t = threading.Thread(target=serve_flask, daemon=True); t.start()

    setup_gpio()
    app = PiFiApp()

    def _auth_ready(dt):
        auth = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=None,
            redirect_uri=REDIRECT_URI,
            scope=SCOPES,
            cache_path=os.path.expanduser('~/.cache/pi_fi_spotipy'),
            open_browser=False,
            show_dialog=False
        )
        token_info = auth.validate_token(auth.get_cached_token())
        if not token_info:
            oauth_or_show_qr(auth)
            def poll_token(_dt):
                ti = auth.validate_token(auth.get_cached_token())
                if ti:
                    Clock.unschedule(poll_token)
                    finish_login()
            Clock.schedule_interval(poll_token, 1.0)
        else:
            finish_login()

    def finish_login():
        global SPOTIFY
        SPOTIFY = build_spotify_client()
        ensure_device()
        pls = fetch_playlists()
        app.root.populate_playlists(pls)

    Clock.schedule_once(_auth_ready, 0.5)
    app.run()

if __name__ == '__main__':
    try:
        main()
    finally:
        if HW:
            GPIO.cleanup()
