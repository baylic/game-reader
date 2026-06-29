import json
import os

CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'GameReader')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')

DEFAULT_CONFIG = {
    "region": None,
    "hotkey_select": "ctrl+shift+r",
    "hotkey_read": "ctrl+shift+t",
    "hotkey_stop": "ctrl+shift+s",
    "hotkey_quit": "ctrl+shift+q",
    "hotkey_cycle": "ctrl+shift+v",
    "tts_voice": "bf_emma",
    "tts_speed": 1.0,
    # Continuously OCR the region in the background so a read can use cached text
    # when the screen hasn't changed (lower keystroke-to-voice latency, light CPU).
    "prefetch_ocr": True,
}

_config = dict(DEFAULT_CONFIG)


def load():
    global _config
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                saved = json.load(f)
            _config = {**DEFAULT_CONFIG, **saved}
        except Exception:
            _config = dict(DEFAULT_CONFIG)
    else:
        _config = dict(DEFAULT_CONFIG)


def save():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(_config, f, indent=2)


def get_region():
    return _config.get('region')


def save_region(x, y, w, h):
    _config['region'] = {"x": x, "y": y, "w": w, "h": h}
    save()


def get(key, default=None):
    return _config.get(key, default)
