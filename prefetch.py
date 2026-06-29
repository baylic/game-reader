"""Background OCR cache.

Continuously captures the saved region and re-OCRs it only when the pixels
change (detected via a cheap frame hash), caching the latest text. A read can
then skip OCR entirely when the screen hasn't changed since the last capture,
cutting keystroke-to-voice latency for static text (quest logs, tooltips, item
cards). The read path still re-hashes the live frame and falls back to OCR-now
on a miss, so cached text can never be stale relative to what's on screen.
"""

import threading
import time
import zlib

import capture
import ocr

_INTERVAL = 0.25  # seconds between background captures

_lock = threading.Lock()
_last_hash: int | None = None
_last_text: str | None = None

_get_region = None
_stop = threading.Event()


def frame_hash(img) -> int:
    return zlib.crc32(img.tobytes())


def note(h: int, text: str):
    """Record the text for a given frame hash (called by the loop and read misses)."""
    global _last_hash, _last_text
    with _lock:
        _last_hash = h
        _last_text = text


def lookup(h: int) -> str | None:
    """Return cached text if it matches the current frame hash, else None."""
    with _lock:
        if h == _last_hash:
            return _last_text
    return None


def _loop():
    while not _stop.is_set():
        region = _get_region() if _get_region else None
        if region:
            try:
                img = capture.capture_region(region)
                h = frame_hash(img)
                with _lock:
                    unchanged = (h == _last_hash)
                if not unchanged and not capture.is_black_frame(img):
                    note(h, ocr.run_ocr(img))
            except Exception:
                pass  # transient capture/OCR error — just try again next tick
        _stop.wait(_INTERVAL)


def start(get_region):
    """Begin background prefetching. get_region is a callable returning the region dict."""
    global _get_region
    _get_region = get_region
    _stop.clear()
    threading.Thread(target=_loop, daemon=True).start()


def stop():
    _stop.set()
