"""
Global configuration — override via environment variables or .env file.
"""
from __future__ import annotations
from typing import List
from pydantic_settings import BaseSettings


def _detect_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class Settings(BaseSettings):
    # ── Server ──────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080", "*"]
    LOG_LEVEL: str = "INFO"

    # ── Device ──────────────────────────────────────────────────────────────
    DEVICE: str = "cpu"   # CTranslate2 & torch share OpenMP — keep cpu to avoid conflict

    # ── VAD (silero-vad) ────────────────────────────────────────────────────
    VAD_THRESHOLD: float = 0.5
    VAD_SAMPLING_RATE: int = 16000
    VAD_MIN_SILENCE_MS: int = 500

    # ── STT (faster-whisper) ────────────────────────────────────────────────
    WHISPER_MODEL_SIZE: str = "tiny"    # tiny | base | small | medium
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "ko"

    # ── Emotion ─────────────────────────────────────────────────────────────
    EMOTION_LABELS: List[str] = ["neutral", "happy", "sad", "angry", "excited", "calm"]
    EMOTION_AUDIO_WEIGHT: float = 0.6
    EMOTION_TEXT_WEIGHT: float = 0.4

    # ── TTS ─────────────────────────────────────────────────────────────────
    # Engine: "say" (macOS native, instant) | "coqui" | "piper" | "xtts"
    TTS_ENGINE: str = "say"
    TTS_SAY_VOICE: str = "Yuna"         # macOS Korean voice
    TTS_COQUI_MODEL: str = "tts_models/en/ljspeech/vits"
    TTS_PIPER_MODEL: str = "models/tts/en_US-lessac-medium.onnx"
    TTS_SAMPLE_RATE: int = 22050

    # ── Metrics ─────────────────────────────────────────────────────────────
    METRICS_LOG_PATH: str = "logs/metrics.jsonl"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
