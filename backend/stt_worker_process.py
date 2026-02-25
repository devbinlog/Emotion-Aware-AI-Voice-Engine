"""
STT Worker Process — runs as a persistent subprocess.

Completely isolated from uvicorn's asyncio event loop, preventing
CTranslate2 ↔ asyncio thread-pool conflict on macOS.

Protocol (stdin/stdout, line-delimited JSON):
  → {"audio_b64": "<base64 float32>", "language": "ko", "sr": 16000}
  ← {"transcript": str, "segments": [...], "language": str}
  ← {"error": str}  on failure
  ← {"type": "ready"}  once model is loaded
"""
import sys
import os
import json
import base64

# Must be set before ctranslate2 loads OpenMP
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

def main():
    model_size   = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    device       = sys.argv[2] if len(sys.argv) > 2 else "cpu"
    compute_type = sys.argv[3] if len(sys.argv) > 3 else "int8"

    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    # Signal that we're ready
    sys.stdout.write(json.dumps({"type": "ready"}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req     = json.loads(line)
            audio   = np.frombuffer(base64.b64decode(req["audio_b64"]), dtype=np.float32).copy()
            lang    = req.get("language") or None

            segs, info = model.transcribe(
                audio,
                language=lang,
                beam_size=5,
                vad_filter=False,
                word_timestamps=False,
            )
            segments = [
                {
                    "start":      round(s.start, 2),
                    "end":        round(s.end, 2),
                    "text":       s.text.strip(),
                    "confidence": round(float(s.avg_logprob), 4),
                }
                for s in segs
            ]
            transcript = "".join(s["text"] for s in segments).strip()
            result = {
                "transcript": transcript,
                "segments":   segments,
                "language":   info.language,
                "latency_ms": 0.0,
            }
        except Exception as e:
            result = {"error": str(e)}

        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
