import os
import re
import subprocess
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

_stop_event = threading.Event()
_kokoro_pipeline = None
_active_voice = 'dagoth'

VOICES = ['emma', 'dagoth', 'narrator']
VOICE_LABELS = {'emma': 'Emma', 'dagoth': 'Dagoth Ur', 'narrator': 'Narrator'}
# Voices that route Kokoro output through an RVC model (key -> worker model_key)
RVC_MODELS = {'dagoth': 'dagoth', 'narrator': 'narrator'}
# Per-voice Kokoro speed override; voices not listed use the caller's speed.
VOICE_SPEED = {'narrator': 0.8}

_RVC_PYTHON = os.path.join(os.path.dirname(__file__), 'rvc_env', 'Scripts', 'python.exe')
_RVC_WORKER = os.path.join(os.path.dirname(__file__), 'rvc_worker.py')

_rvc_proc = None
_rvc_lock = threading.Lock()
_rvc_ready = threading.Event()


def _start_rvc_worker():
    global _rvc_proc
    with _rvc_lock:
        if _rvc_proc is not None and _rvc_proc.poll() is None:
            return  # already running
        _rvc_ready.clear()
        proc = subprocess.Popen(
            [_RVC_PYTHON, _RVC_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        # Drain stdout until we see "ready" (rvc_python prints its own lines first)
        for _ in range(50):
            line = proc.stdout.readline().strip()
            if line == "ready":
                break
            if proc.poll() is not None:
                raise RuntimeError("RVC worker exited before becoming ready")
        else:
            proc.kill()
            raise RuntimeError("RVC worker never sent 'ready'")
        _rvc_proc = proc
        _rvc_ready.set()
        print("RVC voices ready.")


def init():
    global _kokoro_pipeline
    os.environ['HF_HUB_OFFLINE'] = '1'
    print("Loading Kokoro TTS model...")
    from kokoro import KPipeline
    _kokoro_pipeline = KPipeline(lang_code='b')
    print("Kokoro TTS ready.")
    # Pre-warm RVC worker in background so Dagoth Ur is instant on first use
    threading.Thread(target=_start_rvc_worker, daemon=True).start()


def cycle_voice() -> str:
    global _active_voice
    idx = VOICES.index(_active_voice)
    _active_voice = VOICES[(idx + 1) % len(VOICES)]
    label = VOICE_LABELS[_active_voice]
    print(f"Voice switched to: {label}")
    return label


def get_active_label() -> str:
    return VOICE_LABELS[_active_voice]


def _clean(text: str) -> str:
    text = re.sub(r'\n+', ' ', text)
    return re.sub(r' +', ' ', text).strip()


def _play(audio: np.ndarray, sr: int):
    sd.play(audio, samplerate=sr)
    duration = len(audio) / sr
    start = time.time()
    while time.time() - start < duration + 0.5:
        if _stop_event.is_set():
            sd.stop()
            return
        time.sleep(0.05)


def _kokoro_to_numpy(text: str, voice: str, speed: float) -> np.ndarray | None:
    chunks = []
    for _, _, audio in _kokoro_pipeline(text, voice=voice, speed=speed):
        if _stop_event.is_set():
            return None
        if audio is not None:
            chunks.append(audio.cpu().numpy())
    if not chunks:
        return None
    return np.concatenate(chunks)


def _rvc_convert(audio: np.ndarray, model_key: str) -> tuple[np.ndarray, int] | None:
    global _rvc_proc
    tmp_in = os.path.join(tempfile.gettempdir(), 'rvc_in.wav')
    tmp_out = os.path.join(tempfile.gettempdir(), 'rvc_out.wav')
    sf.write(tmp_in, audio, 24000)

    _rvc_ready.wait()  # block until worker is loaded (happens in background at startup)
    with _rvc_lock:
        if _rvc_proc is None or _rvc_proc.poll() is not None:
            print("RVC worker died, restarting...")
            _start_rvc_worker()
        _rvc_proc.stdin.write(f"{model_key}|{tmp_in}|{tmp_out}\n")
        _rvc_proc.stdin.flush()
        response = _rvc_proc.stdout.readline().strip()

    if response != "ok":
        print(f"RVC worker error: {response}")
        return None
    out_audio, out_sr = sf.read(tmp_out)
    return out_audio.astype(np.float32), out_sr


def _speak_emma(text: str, voice: str, speed: float):
    audio = _kokoro_to_numpy(text, voice, speed)
    if audio is None or _stop_event.is_set():
        return
    _play(audio, 24000)


def _speak_rvc(text: str, voice: str, speed: float, model_key: str):
    audio = _kokoro_to_numpy(text, voice, speed)
    if audio is None or _stop_event.is_set():
        return
    result = _rvc_convert(audio, model_key)
    if result is None:
        _play(audio, 24000)  # fallback to Emma if RVC fails
        return
    out_audio, out_sr = result
    if _stop_event.is_set():
        return
    _play(out_audio, out_sr)


def speak(text: str, voice: str = 'bf_emma', speed: float = 1.0):
    _stop_event.clear()
    text = _clean(text)
    speed = VOICE_SPEED.get(_active_voice, speed)
    try:
        model_key = RVC_MODELS.get(_active_voice)
        if model_key is not None:
            _speak_rvc(text, voice, speed, model_key)
        else:
            _speak_emma(text, voice, speed)
    except Exception as e:
        print(f"TTS error: {e}")


def stop():
    _stop_event.set()
    try:
        sd.stop()
    except Exception:
        pass
