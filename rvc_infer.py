"""
RVC inference worker — run in rvc_env (Python 3.10).
Usage: python rvc_infer.py <input_wav> <output_wav> [f0up_key]
"""
import sys
import os

input_wav = sys.argv[1]
output_wav = sys.argv[2]
f0up_key = int(sys.argv[3]) if len(sys.argv) > 3 else -12

_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Applio", "logs", "dagoth_ur")
MODEL_PATH = os.path.join(_base, "dagoth_ur_v2.pth")
INDEX_PATH = os.path.join(_base, "dagoth_ur.index")

from rvc_python.infer import RVCInference

rvc = RVCInference(device="cuda:0")
rvc.load_model(MODEL_PATH, version="v2", index_path=INDEX_PATH)
rvc.set_params(
    f0method="rmvpe",
    f0up_key=f0up_key,
    index_rate=0.75,
    filter_radius=3,
    resample_sr=0,
    rms_mix_rate=1,
    protect=0.33,
)
rvc.infer_file(input_wav, output_wav)
