"""
TTS Service — emotion-conditioned speech synthesis.

MVP Engine: Coqui TTS (tts_models/en/ljspeech/vits)
  - Pure pip install (no external binary)
  - CPU-safe (~1-3s on modern CPU)
  - Modular: swap engine via TTS_ENGINE env var

Emotion conditioning (MVP approach):
  No direct emotion embedding on VITS by default.
  Instead, post-process synthesized audio with librosa:
    - pitch shift   (n_steps)
    - time stretch  (rate)
    - energy scale  (amplitude ×)

  Intensity [0,1] linearly scales each modifier:
    modifier = 1 + (target - 1) × intensity   (for multiplicative params)
    modifier = target × intensity               (for additive params like pitch)

Extension path:
  - XTTS v2: multilingual (Korean), voice cloning → needs GPU
  - VITS fine-tune: train on emotion-labeled Korean corpus
  - Piper: ONNX, ~150ms on CPU (fastest), limited Korean models

See reports/model_choices.md for full comparison.
"""
from __future__ import annotations
import io
import os
import time
import tempfile
import subprocess
import numpy as np
import soundfile as sf
from typing import Dict, Generator, Optional

from app.config import settings
from app.utils.logging import logger

# ── Emotion → prosody modifier table ─────────────────────────────────────────
# Keys:  rate  = time-stretch factor  (1.0 = normal)
#        pitch = semitone shift       (0 = no shift)
#        energy= amplitude scale     (1.0 = normal)
EMOTION_PROSODY: Dict[str, Dict[str, float]] = {
    "neutral": {"rate": 1.00,  "pitch":  0.0, "energy": 1.00},
    "happy":   {"rate": 1.10,  "pitch":  2.0, "energy": 1.20},
    "sad":     {"rate": 0.85,  "pitch": -3.0, "energy": 0.80},
    "angry":   {"rate": 1.15,  "pitch":  1.0, "energy": 1.40},
    "excited": {"rate": 1.20,  "pitch":  4.0, "energy": 1.30},
    "calm":    {"rate": 0.90,  "pitch": -1.0, "energy": 0.90},
}


class TTSService:
    def __init__(self, engine: Optional[str] = None):
        self.engine = engine or settings.TTS_ENGINE
        self._model = None

    # ── Lazy load ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._model is not None:
            return

        if self.engine == "say":
            pass  # subprocess only, no model to load

        elif self.engine == "coqui":
            from TTS.api import TTS as CoquiTTS

            logger.info(f"TTS: loading Coqui VITS ({settings.TTS_COQUI_MODEL}) …")
            self._model = CoquiTTS(
                model_name=settings.TTS_COQUI_MODEL,
                progress_bar=False,
                gpu=(settings.DEVICE == "cuda"),
            )
            logger.info("TTS: Coqui model ready")

        elif self.engine == "xtts":
            from TTS.api import TTS as CoquiTTS

            logger.info("TTS: loading XTTS v2 (multilingual, needs GPU for speed) …")
            self._model = CoquiTTS(
                "tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False,
                gpu=(settings.DEVICE == "cuda"),
            )
        # piper: subprocess; no Python object to load

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        emotion_label: str = "neutral",
        intensity: float = 0.5,
        speaker: Optional[str] = None,
        language: str = "en",
        voice: Optional[str] = None,
    ) -> Dict:
        """
        Synthesize speech, apply emotion prosody post-processing.

        Returns:
            {
                "audio"        : np.ndarray (float32),
                "sample_rate"  : int,
                "latency_ms"   : float,
                "emotion_label": str,
                "intensity"    : float,
            }
        """
        t0 = time.time()
        self._load()

        if self.engine == "say":
            audio, sr = self._synth_say(text, voice=voice)
        elif self.engine == "piper":
            audio, sr = self._synth_piper(text)
        else:
            audio, sr = self._synth_coqui(text, speaker, language)

        # Apply emotion prosody modifiers
        audio = self._apply_prosody(audio, sr, emotion_label, intensity)

        latency_ms = (time.time() - t0) * 1000
        logger.info(f"TTS: {emotion_label}@{intensity:.2f} → {latency_ms:.0f}ms")

        return {
            "audio":         audio,
            "sample_rate":   sr,
            "latency_ms":    round(latency_ms, 2),
            "emotion_label": emotion_label,
            "intensity":     intensity,
        }

    def synthesize_chunks(
        self,
        text: str,
        emotion_label: str = "neutral",
        intensity: float = 0.5,
        chunk_ms: int = 250,
    ) -> Generator[tuple[np.ndarray, int], None, None]:
        """
        Generate audio in chunks of chunk_ms milliseconds.
        Useful for WebSocket streaming.
        """
        result = self.synthesize(text, emotion_label, intensity)
        audio, sr = result["audio"], result["sample_rate"]
        chunk_samples = int(sr * chunk_ms / 1000)

        for start in range(0, len(audio), chunk_samples):
            yield audio[start : start + chunk_samples], sr

    # ── Engine backends ───────────────────────────────────────────────────────

    def _synth_say(self, text: str, voice: Optional[str] = None) -> tuple[np.ndarray, int]:
        """macOS built-in TTS via `say -o <file>.aiff`. No afconvert needed."""
        voice = voice or getattr(settings, "TTS_SAY_VOICE", "Yuna")
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
            aiff_path = f.name
        try:
            # say → AIFF directly (soundfile can read AIFF natively)
            subprocess.run(
                ["say", "-v", voice, "-r", "200", "-o", aiff_path, text],
                check=True, capture_output=True, timeout=20,
            )
            audio, sr = sf.read(aiff_path, dtype="float32")
        finally:
            if os.path.exists(aiff_path):
                os.unlink(aiff_path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32), sr

    def _synth_coqui(
        self,
        text: str,
        speaker: Optional[str],
        language: str,
    ) -> tuple[np.ndarray, int]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        try:
            kwargs: Dict = {"text": text, "file_path": out_path}
            if speaker:
                kwargs["speaker"] = speaker
            # XTTS needs language kwarg; VITS ignores it silently
            if self.engine == "xtts":
                kwargs["language"] = language
            self._model.tts_to_file(**kwargs)
            audio, sr = sf.read(out_path, dtype="float32")
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32), sr

    def _synth_piper(self, text: str) -> tuple[np.ndarray, int]:
        model_path = settings.TTS_PIPER_MODEL
        config_path = model_path + ".json"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        try:
            result = subprocess.run(
                ["piper", "--model", model_path, "--config", config_path,
                 "--output_file", out_path],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"piper error: {result.stderr.decode()}")
            audio, sr = sf.read(out_path, dtype="float32")
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)
        return audio.astype(np.float32), sr

    # ── Prosody post-processing ───────────────────────────────────────────────

    def _apply_prosody(
        self,
        audio: np.ndarray,
        sr: int,
        emotion_label: str,
        intensity: float,
    ) -> np.ndarray:
        """
        Interpolate prosody modifiers using scipy (no librosa dependency).

        rate'   = 1.0 + (rate_target  - 1.0) × intensity  → scipy resample
        pitch'  = pitch_target × intensity                  → resample + SR fix
        energy' = 1.0 + (energy_target - 1.0) × intensity  → amplitude scale
        """
        from scipy.signal import resample_poly
        from math import gcd

        params  = EMOTION_PROSODY.get(emotion_label, EMOTION_PROSODY["neutral"])
        neutral = EMOTION_PROSODY["neutral"]

        rate   = 1.0 + (params["rate"]   - neutral["rate"])   * intensity
        pitch  =        params["pitch"]                        * intensity
        energy = 1.0 + (params["energy"] - neutral["energy"]) * intensity

        try:
            # Time-stretch via rational resample
            if abs(rate - 1.0) > 0.02:
                # Approximate rate as a rational p/q (precision: 1/200)
                denom = 200
                numer = max(1, round(rate * denom))
                g = gcd(numer, denom)
                audio = resample_poly(audio, denom // g, numer // g)

            # Pitch-shift = resample then re-stretch to original length
            if abs(pitch) > 0.1:
                factor = 2 ** (pitch / 12.0)
                denom  = 200
                numer  = max(1, round(factor * denom))
                g      = gcd(numer, denom)
                shifted = resample_poly(audio, numer // g, denom // g)
                # Restore original length by resampling back
                orig_len = len(audio)
                if len(shifted) != orig_len:
                    audio = resample_poly(shifted, orig_len, len(shifted)) if len(shifted) > 0 else audio
                else:
                    audio = shifted

        except Exception as e:
            logger.warning(f"TTS prosody mod failed: {e}")

        if abs(energy - 1.0) > 0.01:
            audio = np.clip(audio * energy, -1.0, 1.0)

        return audio.astype(np.float32)
