# Game Reader

A Windows desktop tool that lets you select a region of your screen, then press a hotkey to have the text read aloud. Built for games — works in borderless windowed mode, remembers your selected region across sessions, and runs silently in the system tray.

Comes with two voices:
- **Emma** — natural British female voice (Kokoro TTS, runs fully locally on GPU)
- **Dagoth Ur** — trained RVC voice model from Morrowind, converted from Emma's speech

Everything runs locally. No API keys, no internet required after setup.

---

## What it does

- Draw a box over any text on screen (quest text, tooltips, subtitles, item descriptions)
- Press a hotkey — the text gets OCR'd and read aloud
- The region is saved so you only draw it once
- Switch between Emma and Dagoth Ur voices with a hotkey
- Stop playback instantly with another hotkey

---

## Requirements

- Windows 10/11
- Python 3.11 — [python.org](https://www.python.org/downloads/)
- Python 3.10 (for the RVC voice env) — [python.org](https://www.python.org/downloads/release/python-31011/)
- NVIDIA GPU with CUDA (for Kokoro TTS and RVC inference) — CPU fallback works but is slow
- [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) — install to `C:\Program Files\Tesseract-OCR\`, select English language data during install
- Must be run as **Administrator** (required for global hotkeys)

---

## Setup

### 1. Clone the repo

```
git clone https://github.com/baylic/game-reader.git
cd game-reader
```

### 2. Install main Python dependencies

```
pip install -r requirements.txt
pip install torch==2.11.0+cu128 torchvision==0.26.0+cu128 torchaudio==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

> If you don't have a CUDA GPU, skip the second line — CPU torch from requirements.txt will be used automatically.

### 3. Set up the RVC voice environment (for Dagoth Ur voice)

```
py -3.10 -m venv rvc_env
rvc_env\Scripts\pip install rvc-python
```

### 4. Get the Dagoth Ur voice model

Download `dagoth_ur_v2.pth` and `dagoth_ur.index` from the [Releases page](https://github.com/baylic/game-reader/releases) and place them at:

```
game-reader\Applio\logs\dagoth_ur\dagoth_ur_v2.pth
game-reader\Applio\logs\dagoth_ur\dagoth_ur.index
```

You will need to create the `Applio\logs\dagoth_ur\` folder manually if it doesn't exist.

### 5. Run as Administrator

Right-click your terminal → "Run as administrator", then:

```
python main.py
```

---

## Hotkeys

| Hotkey | Action |
|---|---|
| Ctrl+Shift+R | Draw selection region on screen |
| Ctrl+Shift+T | Read selected region aloud |
| Ctrl+Shift+S | Stop playback |
| Ctrl+Shift+V | Cycle between Emma / Dagoth Ur |
| Ctrl+Shift+Q | Quit |

---

## First run notes

- **Kokoro model** (~330MB) downloads automatically on first launch from HuggingFace and is cached locally. Subsequent launches use the cache with no internet needed.
- **Dagoth Ur first call** takes ~7 seconds while CUDA compiles kernels. Every call after that takes ~4 seconds.
- The region you select with Ctrl+Shift+R is saved to `%APPDATA%\GameReader\config.json` and restored on next launch.

---

## Gaming tips

- Use **Borderless Windowed** mode — overlays don't work over exclusive fullscreen
- Select your region over an in-game text area (quest log, dialogue box, tooltip)
- If OCR is misreading text, try selecting a tighter region around just the text

---

## Training your own RVC voice

The Dagoth Ur voice was trained using [Applio](https://github.com/IAHispano/Applio). If you want to train a different voice:

1. Put ~20 seconds of clean audio in `Applio\logs\<name>\sliced_audios\` (16-bit WAV, 40kHz)
2. Follow the Applio preprocessing and feature extraction steps
3. Run training with `python Applio\run_train.py`
4. Export the model with `python Applio\export_model.py`

---

## File structure

```
game-reader/
  main.py          — entry point, hotkeys, system tray
  overlay.py       — fullscreen transparent region selector
  capture.py       — screen capture (mss)
  ocr.py           — Tesseract OCR + preprocessing
  tts.py           — dual-voice TTS (Kokoro + RVC)
  config.py        — persistent config (region, hotkeys, voice)
  rvc_worker.py    — persistent RVC subprocess worker
  rvc_infer.py     — RVC inference script (runs in rvc_env)
  requirements.txt
```
