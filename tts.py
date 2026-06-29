import os
import queue
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


def _warm_rvc():
    # Run one throwaway conversion at startup so CUDA kernels compile now (in the
    # background) instead of on the user's first read (~6s first call -> ~0.5s after).
    try:
        dummy = (np.random.randn(int(24000 * 1.0)).astype(np.float32) * 0.01)
        _rvc_convert(dummy, 'dagoth')
        print("RVC warmed up.")
    except Exception as e:
        print(f"RVC warm-up skipped: {e}")


def _start_and_warm():
    _start_rvc_worker()
    _warm_rvc()


def init():
    global _kokoro_pipeline
    os.environ['HF_HUB_OFFLINE'] = '1'
    print("Loading Kokoro TTS model...")
    from kokoro import KPipeline
    _kokoro_pipeline = KPipeline(lang_code='b')
    print("Kokoro TTS ready.")
    # Pre-warm RVC worker + compile CUDA kernels in background so the first read is instant
    threading.Thread(target=_start_and_warm, daemon=True).start()


def cycle_voice() -> str:
    global _active_voice
    idx = VOICES.index(_active_voice)
    _active_voice = VOICES[(idx + 1) % len(VOICES)]
    label = VOICE_LABELS[_active_voice]
    print(f"Voice switched to: {label}")
    return label


def get_active_label() -> str:
    return VOICE_LABELS[_active_voice]


# Leading "Speaker Name:" label — 1–4 capitalised words then a colon, with
# actual dialogue following. Matches e.g. "Astarion:", "The Narrator:", "Lae'zel:".
_SPEAKER_RE = re.compile(r"^[A-Z][\w'’.\-]*(?:\s+[A-Z][\w'’.\-]*){0,3}\s*:\s*(?=\S)")


def _strip_speaker(text: str) -> str:
    # Drop a leading speaker name so only the spoken line is read aloud.
    m = _SPEAKER_RE.match(text)
    if m and m.end() < len(text):
        return text[m.end():]
    return text


def _clean(text: str) -> str:
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r' +', ' ', text).strip()
    return _strip_speaker(text)


def _play(audio: np.ndarray, sr: int, tail: float = 0.5):
    sd.play(audio, samplerate=sr)
    duration = len(audio) / sr
    start = time.time()
    while time.time() - start < duration + tail:
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
    # Pipeline by sentence: a background thread generates each Kokoro segment and
    # RVC-converts it, while this thread plays segments as soon as they're ready.
    # Cuts time-to-first-audio to roughly one sentence instead of the whole passage.
    audio_q: queue.Queue = queue.Queue(maxsize=4)

    def _put(item) -> bool:
        # Enqueue, but bail out if playback was stopped so we never block forever
        # on a full queue after the consumer has exited.
        while not _stop_event.is_set():
            try:
                audio_q.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def produce():
        try:
            for _, _, audio in _kokoro_pipeline(text, voice=voice, speed=speed):
                if _stop_event.is_set():
                    return
                if audio is None:
                    continue
                seg = audio.cpu().numpy()
                result = _rvc_convert(seg, model_key)
                if result is None:
                    result = (seg, 24000)  # fallback to Emma segment if RVC fails
                if not _put(result):
                    return
        finally:
            _put(None)  # sentinel: no more segments

    threading.Thread(target=produce, daemon=True).start()

    while not _stop_event.is_set():
        item = audio_q.get()
        if item is None:
            return
        out_audio, out_sr = item
        _play(out_audio, out_sr, tail=0.1)  # small tail keeps sentences gapless


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
