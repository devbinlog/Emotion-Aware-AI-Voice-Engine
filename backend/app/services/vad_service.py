"""
VAD Service — silero-vad (torch.hub).

Provides:
  - detect(audio) → full-audio segment list
  - is_speech_chunk(chunk) → (bool, confidence) for real-time streaming

Graceful fallback: if silero-vad unavailable, returns whole audio as speech.
"""
from __future__ import annotations
import time
import numpy as np
from typing import Dict, List, Tuple
from app.utils.logging import logger


class VADService:
    """
    Wraps silero-vad with lazy loading.
    Thread-safe for single-process async usage (FastAPI + uvicorn).
    """

    def __init__(
        self,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 500,
    ):
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.min_silence_duration_ms = min_silence_duration_ms
        self._model = None
        self._get_speech_timestamps = None
        self._available = True

    # ── Private ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._model is not None or not self._available:
            return
        try:
            import torch  # lazy — only if silero-vad is actually needed
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                verbose=False,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]
            logger.info("VAD: silero-vad loaded")
        except Exception as e:
            logger.warning(f"VAD: silero-vad unavailable ({e}). Using fallback.")
            self._available = False

    # ── Public API ───────────────────────────────────────────────────────────

    def detect(self, audio: np.ndarray) -> Dict:
        """
        Run VAD on a full audio array.

        Returns:
            {
                "segments": [{"start": float, "end": float}, ...],   # seconds
                "speech_detected": bool,
                "latency_ms": float,
            }
        """
        self._load()
        t0 = time.time()

        if not self._available:
            # Fallback: treat entire clip as speech
            duration = len(audio) / self.sampling_rate
            return {
                "segments": [{"start": 0.0, "end": duration}],
                "speech_detected": True,
                "latency_ms": 0.0,
            }

        import torch
        tensor = torch.FloatTensor(audio)
        try:
            timestamps = self._get_speech_timestamps(
                tensor,
                self._model,
                threshold=self.threshold,
                sampling_rate=self.sampling_rate,
                min_silence_duration_ms=self.min_silence_duration_ms,
                return_seconds=True,
            )
        except Exception as e:
            logger.warning(f"VAD detect error: {e}")
            timestamps = []

        latency_ms = (time.time() - t0) * 1000
        return {
            "segments": [{"start": t["start"], "end": t["end"]} for t in timestamps],
            "speech_detected": len(timestamps) > 0,
            "latency_ms": round(latency_ms, 2),
        }

    def is_speech_chunk(self, chunk: np.ndarray) -> Tuple[bool, float]:
        """
        Fast per-chunk classification for real-time streaming.

        Returns: (is_speech: bool, confidence: float 0-1)
        """
        self._load()

        if not self._available:
            return True, 1.0

        if len(chunk) < 512:
            chunk = np.pad(chunk, (0, 512 - len(chunk)))

        import torch
        tensor = torch.FloatTensor(chunk[:512])
        try:
            confidence: float = self._model(tensor, self.sampling_rate).item()
        except Exception:
            return True, 1.0

        return confidence > self.threshold, round(confidence, 3)
