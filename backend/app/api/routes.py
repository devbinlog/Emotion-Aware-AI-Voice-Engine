"""
HTTP REST endpoints.

POST /api/transcribe        → STT
POST /api/analyze-emotion   → Emotion analysis
POST /api/synthesize        → TTS (returns audio/wav)
GET  /api/metrics           → Pipeline latency history
"""
from __future__ import annotations
import io
import uuid
from typing import Optional, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.audio_io import load_audio_bytes, audio_to_bytes
from app.services.stt_service import STTService
from app.services.emotion_service import EmotionService
from app.services.tts_service import TTSService
from app.utils.metrics import MetricsTracker
from app.utils.logging import logger

router = APIRouter()

# ── Lazy service singletons ──────────────────────────────────────────────────
_stt:     Optional[STTService]     = None
_emotion: Optional[EmotionService] = None
_tts:     Optional[TTSService]     = None


def _get_stt()     -> STTService:
    global _stt;     _stt     = _stt     or STTService();     return _stt
def _get_emotion() -> EmotionService:
    global _emotion; _emotion = _emotion or EmotionService(); return _emotion
def _get_tts()     -> TTSService:
    global _tts;     _tts     = _tts     or TTSService();     return _tts


# ── POST /api/transcribe ─────────────────────────────────────────────────────
# Request:  multipart — file: audio, language?: str
# Response: TranscribeResponse

class SegmentSchema(BaseModel):
    start:      float
    end:        float
    text:       str
    confidence: float

class TranscribeResponse(BaseModel):
    transcript:  str
    segments:    List[SegmentSchema]
    language:    str
    latency_ms:  float


@router.post("/transcribe", response_model=TranscribeResponse, summary="Speech-to-Text")
async def transcribe(
    file: UploadFile     = File(..., description="Audio file (wav/mp3/ogg/flac)"),
    language: Optional[str] = Form(None, description="ISO-639-1 code, e.g. 'ko'. Omit for auto."),
):
    """STT: upload audio → transcript + segment timestamps."""
    raw = await file.read()
    try:
        audio, sr = load_audio_bytes(raw)
    except Exception as e:
        raise HTTPException(400, f"Audio decode error: {e}")

    result = _get_stt().transcribe(audio, language=language, sample_rate=sr)
    return TranscribeResponse(**result)


# ── POST /api/analyze-emotion ────────────────────────────────────────────────

class EmotionResponse(BaseModel):
    emotion_label:    str
    intensity:        float = Field(..., ge=0.0, le=1.0)
    probabilities:    dict
    features_summary: dict
    branches:         dict
    latency_ms:       float


@router.post("/analyze-emotion", response_model=EmotionResponse, summary="Emotion Analysis")
async def analyze_emotion(
    file: UploadFile          = File(...),
    transcript: Optional[str] = Form(None, description="Optional STT transcript for text fusion"),
):
    """
    Emotion analysis:
    - audio prosody features (f0, rms, zcr, mfcc, speaking_rate)
    - optional text sentiment fusion
    Returns emotion_label ∈ [neutral,happy,sad,angry,excited,calm] + intensity 0-1.
    """
    raw = await file.read()
    try:
        audio, sr = load_audio_bytes(raw)
    except Exception as e:
        raise HTTPException(400, f"Audio decode error: {e}")

    result = _get_emotion().analyze(audio, sr=sr, transcript=transcript)
    return EmotionResponse(**result)


# ── POST /api/synthesize ─────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text:          str   = Field(..., min_length=1)
    emotion_label: str   = Field("neutral", description="One of: neutral happy sad angry excited calm")
    intensity:     float = Field(0.5, ge=0.0, le=1.0)
    speaker:       Optional[str] = None
    language:      str   = Field("en", description="Language code for multilingual TTS")


@router.post("/synthesize", summary="Text-to-Speech with Emotion Conditioning")
async def synthesize(req: SynthesizeRequest):
    """
    TTS: text + emotion → audio/wav (streaming).
    Response headers include X-Latency-Ms, X-Emotion, X-Intensity.
    """
    try:
        result = _get_tts().synthesize(
            text=req.text,
            emotion_label=req.emotion_label,
            intensity=req.intensity,
            speaker=req.speaker,
            language=req.language,
        )
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(500, str(e))

    wav_bytes = audio_to_bytes(result["audio"], result["sample_rate"])
    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={
            "X-Latency-Ms": str(round(result["latency_ms"], 1)),
            "X-Emotion":    result["emotion_label"],
            "X-Intensity":  str(result["intensity"]),
        },
    )


# ── GET /api/voices ──────────────────────────────────────────────────────────

@router.get("/voices", summary="Available TTS Voices")
async def get_voices():
    """Return available macOS say voices grouped by language."""
    import subprocess
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
    lines = (result.stdout + result.stderr).strip().split("\n")

    voices = []
    for line in lines:
        if not line.strip():
            continue
        # Format: "Name    lang_CODE    # sample text"
        parts = line.split("#")[0].strip().split()
        if len(parts) >= 2:
            name = parts[0]
            lang = parts[-1]
            # Keep: Korean, English (US/GB), Japanese, Chinese
            if any(lang.startswith(p) for p in ("ko_", "en_", "ja_", "zh_")):
                voices.append({"name": name, "lang": lang})

    return {"voices": voices, "default": "Yuna"}


# ── GET /api/metrics ─────────────────────────────────────────────────────────

@router.get("/metrics", summary="Pipeline Latency History")
async def get_metrics():
    """Return accumulated pipeline metrics (from logs/metrics.jsonl)."""
    from app.utils.metrics import metrics_tracker
    return {
        "history": metrics_tracker.load_history(),
        "stats":   metrics_tracker.summary_stats(),
    }
