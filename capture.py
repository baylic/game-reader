import ctypes
import mss
from PIL import Image


def get_dpi_scale() -> float:
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def capture_region(region: dict) -> Image.Image:
    """Capture screen region. region dict has x, y, w, h in physical pixels."""
    with mss.mss() as sct:
        monitor = {
            "left": region["x"],
            "top": region["y"],
            "width": region["w"],
            "height": region["h"],
        }
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    return img


def is_black_frame(img: Image.Image) -> bool:
    """Returns True if the captured image is nearly all black (exclusive fullscreen issue)."""
    gray = img.convert('L')
    avg = sum(gray.getdata()) / (gray.width * gray.height)
    return avg < 5
