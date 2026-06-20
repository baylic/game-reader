"""
Persistent RVC worker — run in rvc_env (Python 3.10).
Reads "input_wav|output_wav" lines from stdin, writes "ok" or "err:<msg>" to stdout.
Models stay loaded between calls.
"""
import sys
import os

MODEL_PATH = r"C:\Users\Bayli\game_reader\Applio\logs\dagoth_ur\dagoth_ur_v2.pth"
INDEX_PATH = r"C:\Users\Bayli\game_reader\Applio\logs\dagoth_ur\dagoth_ur.index"
F0UP_KEY = -12

from rvc_python.infer import RVCInference

rvc = RVCInference(device="cuda:0")
rvc.load_model(MODEL_PATH, version="v2", index_path=INDEX_PATH)
rvc.set_params(
    f0method="rmvpe",
    f0up_key=F0UP_KEY,
    index_rate=0.75,
    filter_radius=3,
    resample_sr=0,
    rms_mix_rate=1,
    protect=0.33,
)

sys.stdout.write("ready\n")
sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        input_wav, output_wav = line.split("|", 1)
        rvc.infer_file(input_wav, output_wav)
        sys.stdout.write("ok\n")
    except Exception as e:
        sys.stdout.write(f"err:{e}\n")
    sys.stdout.flush()
