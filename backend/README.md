# Backend — Emotion-Aware AI Voice Engine

FastAPI backend implementing the full voice pipeline:
VAD → STT → Emotion Analysis → Emotion-Conditioned TTS

---

## Quick Start

```bash
cd backend

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure (optional)
cp .env.example .env
# Edit .env: choose TTS_ENGINE, WHISPER_MODEL_SIZE, etc.

# 3. Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` for interactive API docs.

---

## Architecture

```
FastAPI app (main.py)
├── /api
│   ├── POST /api/transcribe        ← STT
│   ├── POST /api/analyze-emotion   ← Emotion
│   ├── POST /api/synthesize        ← TTS (WAV stream)
│   └── GET  /api/metrics           ← Latency history
└── /ws
    └── WS /ws/voice                ← Full streaming pipeline

services/
├── audio_io.py       load/convert/chunk audio arrays
├── vad_service.py    silero-vad (lazy, graceful fallback)
├── stt_service.py    faster-whisper (lazy)
├── emotion_service.py feature extraction + fusion
└── tts_service.py    Coqui/Piper/XTTS + prosody post-proc

models/
└── emotion_classifier.py  rule-based baseline (replaceable)

utils/
├── metrics.py        PipelineMetrics + JSONL persistence
└── logging.py        structured JSON logger
```

---

## API Reference

### `POST /api/transcribe`

```
Content-Type: multipart/form-data
Fields:
  file      : audio file (wav / mp3 / ogg / flac)
  language  : (optional) "ko" | "en" | … (ISO-639-1)

Response 200:
{
  "transcript": "안녕하세요",
  "segments": [{"start": 0.0, "end": 1.4, "text": "안녕하세요", "confidence": -0.23}],
  "language": "ko",
  "latency_ms": 680.4
}
```

### `POST /api/analyze-emotion`

```
Content-Type: multipart/form-data
Fields:
  file       : audio file
  transcript : (optional) STT text for text-branch fusion

Response 200:
{
  "emotion_label": "happy",
  "intensity": 0.74,
  "probabilities": {"neutral": 0.06, "happy": 0.74, "sad": 0.03, ...},
  "features_summary": {"f0_mean": 218.3, "rms_mean": 0.093, ...},
  "branches": {
    "audio": {"emotion_label": "happy", "intensity": 0.68, ...},
    "text":  {"emotion_label": "happy", "intensity": 0.80, ...}
  },
  "latency_ms": 340.1
}
```

### `POST /api/synthesize`

```
Content-Type: application/json
Body:
{
  "text": "안녕하세요!",
  "emotion_label": "happy",
  "intensity": 0.7,
  "speaker": null,
  "language": "en"
}

Response 200: audio/wav (streaming)
Headers: X-Latency-Ms, X-Emotion, X-Intensity
```

### `WS /ws/voice`

See `app/api/websocket.py` docstring for full protocol.

---

## Emotion Model

### Labels
`neutral | happy | sad | angry | excited | calm`

### Audio Features Extracted
| Feature           | Description                          |
|-------------------|--------------------------------------|
| f0_mean / f0_std  | Fundamental frequency statistics (Hz)|
| rms_mean / rms_std| RMS energy statistics                |
| zcr_mean          | Zero-crossing rate                   |
| mfcc_1..13_mean   | MFCC cepstral coefficients           |
| speaking_rate     | Onset events / second                |

### Fusion Strategy
```
fused_prob[c] = 0.6 × p_audio[c] + 0.4 × p_text[c]
intensity     = max(fused_prob)   after L1-normalization
```
Weights configurable via `EMOTION_AUDIO_WEIGHT` / `EMOTION_TEXT_WEIGHT` in `.env`.

### Intensity Definition
- `> 0.70` → strong / clear emotion
- `0.40–0.70` → moderate
- `< 0.40` → weak / ambiguous (skews toward neutral)

### Replacing the Classifier
Override `EmotionClassifier.classify_audio` or `classify_text` in
`app/models/emotion_classifier.py`. Same return schema required:
```python
{"emotion_label": str, "intensity": float, "probabilities": Dict[str, float]}
```

---

## TTS Engine Selection

Default: **Coqui VITS** (CPU-safe, pure pip).

Change `TTS_ENGINE` in `.env`:

| Value    | Latency (CPU) | Install         | Korean |
|----------|---------------|-----------------|--------|
| `coqui`  | ~1–2.5 s      | `pip install TTS` | ✗     |
| `piper`  | ~80–250 ms    | + model download  | ✗     |
| `xtts`   | ~8–20 s CPU   | `pip install TTS` | ✅    |

See `reports/model_choices.md` for full comparison.

---

## Metrics

All pipeline timings are appended to `logs/metrics.jsonl`:

```json
{"session_id": "a1b2c3d4", "vad_detect_ms": 12.3, "stt_ms": 680.1,
 "emotion_ms": 340.2, "tts_ms": 950.5, "total_ms": 2005.3, "timestamp": "..."}
```

Retrieve via `GET /api/metrics` or load with:
```python
from app.utils.metrics import metrics_tracker
print(metrics_tracker.summary_stats())
```

---

## Configuration (`.env`)

| Key                    | Default                              | Description              |
|------------------------|--------------------------------------|--------------------------|
| `TTS_ENGINE`           | `coqui`                              | TTS backend              |
| `WHISPER_MODEL_SIZE`   | `small`                              | STT model size           |
| `WHISPER_LANGUAGE`     | `ko`                                 | STT language (None=auto) |
| `VAD_THRESHOLD`        | `0.5`                                | Speech confidence gate   |
| `EMOTION_AUDIO_WEIGHT` | `0.6`                                | Audio branch weight      |
| `EMOTION_TEXT_WEIGHT`  | `0.4`                                | Text branch weight       |
| `LOG_LEVEL`            | `INFO`                               | Logging verbosity        |
