"""
Persistent RVC worker — run in rvc_env (Python 3.10).
Reads "model_key|input_wav|output_wav" lines from stdin, writes "ok" or "err:<msg>".
One RVCInference instance stays loaded; weights are reloaded only when the
requested model_key differs from the currently-loaded one (load_model ~2s,
set_params instant). Voice switches are rare (hotkey-driven), so this is cheap.

rvc_python prints model-load/inference chatter to stdout. That would desync the
one-line request/response protocol, so we keep a private handle to the real
stdout for protocol messages and point sys.stdout at stderr (DEVNULL in the app).
"""
import sys
import os

_proto = sys.stdout          # protocol channel (ready / ok / err)
sys.stdout = sys.stderr      # send all library prints to stderr instead

_logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Applio", "logs")

# key -> model files + pitch shift
MODELS = {
    "dagoth": {
        "model": os.path.join(_logs, "dagoth_ur", "dagoth_ur_v2.pth"),
        "index": os.path.join(_logs, "dagoth_ur", "dagoth_ur.index"),
        "f0up_key": -12,
    },
    "narrator": {
        "model": os.path.join(_logs, "bg3_narrator", "bg3_narrator_v2.pth"),
        "index": os.path.join(_logs, "bg3_narrator", "bg3_narrator.index"),
        "f0up_key": -6,
    },
}

from rvc_python.infer import RVCInference

rvc = RVCInference(device="cuda:0")
_loaded_key = None


def _ensure_model(key):
    global _loaded_key
    if key == _loaded_key:
        return
    cfg = MODELS[key]
    rvc.load_model(cfg["model"], version="v2", index_path=cfg["index"])
    rvc.set_params(
        f0method="rmvpe",
        f0up_key=cfg["f0up_key"],
        index_rate=0.0,  # skip FAISS index retrieval: ~210ms faster per call (beta)
        filter_radius=3,
        resample_sr=0,
        rms_mix_rate=1,
        protect=0.33,
    )
    _loaded_key = key


def _reply(msg):
    _proto.write(msg + "\n")
    _proto.flush()


# Pre-load the default voice so the first request is instant.
_ensure_model("dagoth")
_reply("ready")

for line in sys.stdin:
    line = line.strip().lstrip("﻿").strip()  # tolerate a stray UTF-8 BOM
    if not line:
        continue
    try:
        model_key, input_wav, output_wav = line.split("|", 2)
        _ensure_model(model_key)
        rvc.infer_file(input_wav, output_wav)
        _reply("ok")
    except Exception as e:
        _reply(f"err:{e}")
