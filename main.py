import ctypes
import queue
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

import keyboard
import pystray
from PIL import Image, ImageDraw

import config
import capture
import ocr
import tts
import overlay

# Must be called before any window creation to fix DPI scaling on high-DPI displays
ctypes.windll.shcore.SetProcessDpiAwareness(2)

_queue: queue.Queue = queue.Queue()
_executor = ThreadPoolExecutor(max_workers=1)
_tray: pystray.Icon | None = None
_root: tk.Tk | None = None


def _make_tray_icon() -> Image.Image:
    img = Image.new('RGB', (64, 64), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.rectangle([5, 5, 59, 59], outline=(0, 200, 200), width=3)
    draw.text((16, 18), 'GR', fill=(0, 200, 200))
    return img


def _read_region():
    region = config.get_region()
    if not region:
        tts.speak(
            "No region selected. Press Control Shift R to select a region.",
            config.get('tts_voice'), config.get('tts_speed', 1.0),
        )
        return
    try:
        img = capture.capture_region(region)
    except Exception as e:
        print(f"Capture error: {e}")
        return
    if capture.is_black_frame(img):
        tts.speak(
            "Screen capture failed. Switch your game to borderless windowed mode.",
            config.get('tts_voice'), config.get('tts_speed', 1.0),
        )
        return
    text = ocr.run_ocr(img)
    if not text:
        tts.speak("No text detected.", config.get('tts_voice'), config.get('tts_speed', 1.0))
        return
    print(f"OCR: {text!r}")
    tts.speak(text, config.get('tts_voice'), config.get('tts_speed', 1.0))


def _on_region_selected(region):
    if region:
        config.save_region(region['x'], region['y'], region['w'], region['h'])
        print(f"Region saved: {region}")
    else:
        print("Region selection cancelled.")


def _cycle_voice():
    label = tts.cycle_voice()
    tts.speak(f"Voice switched to {label}.", config.get('tts_voice'), config.get('tts_speed', 1.0))


def _shutdown():
    tts.stop()
    if _tray:
        _tray.stop()
    if _root:
        _root.after(0, _root.quit)


def _check_queue():
    try:
        while True:
            msg = _queue.get_nowait()
            if msg == 'select':
                overlay.start_overlay(_root, _on_region_selected)
            elif msg == 'quit':
                _root.quit()
                return
    except queue.Empty:
        pass
    _root.after(50, _check_queue)


def _run_tray():
    global _tray
    menu = pystray.Menu(
        pystray.MenuItem('Select Region  (Ctrl+Shift+R)', lambda icon, item: _queue.put('select')),
        pystray.MenuItem('Read Region  (Ctrl+Shift+T)', lambda icon, item: _executor.submit(_read_region)),
        pystray.MenuItem('Stop Speech  (Ctrl+Shift+S)', lambda icon, item: tts.stop()),
        pystray.MenuItem('Quit', lambda icon, item: _shutdown()),
    )
    _tray = pystray.Icon('GameReader', _make_tray_icon(), 'Game Reader', menu)
    _tray.run()


def main():
    global _root

    config.load()
    tts.init()

    keyboard.add_hotkey(config.get('hotkey_select'), lambda: _queue.put('select'))
    keyboard.add_hotkey(config.get('hotkey_read'), lambda: _executor.submit(_read_region))
    keyboard.add_hotkey(config.get('hotkey_stop'), tts.stop)
    keyboard.add_hotkey(config.get('hotkey_cycle'), lambda: _executor.submit(_cycle_voice))
    keyboard.add_hotkey(config.get('hotkey_quit'), _shutdown)

    tray_thread = threading.Thread(target=_run_tray, daemon=True)
    tray_thread.start()

    _root = tk.Tk()
    _root.withdraw()

    print("Game Reader is running.")
    print("  Ctrl+Shift+R  —  Select screen region")
    print("  Ctrl+Shift+T  —  Read selected region aloud")
    print("  Ctrl+Shift+S  —  Stop speech")
    print("  Ctrl+Shift+V  —  Cycle voice (Emma / Dagoth Ur / Narrator)")
    print("  Ctrl+Shift+Q  —  Quit")
    print("Check the system tray for the icon.")

    _root.after(50, _check_queue)
    _root.mainloop()

    _executor.shutdown(wait=False)
    print("Game Reader stopped.")


if __name__ == '__main__':
    main()
