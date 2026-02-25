"""
Audio I/O utilities — numpy / scipy only (no librosa dependency).
"""
from __future__ import annotations
import io
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd
from typing import Generator, Tuple

TARGET_SR = 16000


def load_audio_bytes(audio_bytes: bytes, target_sr: int = TARGET_SR) -> Tuple[np.ndarray, int]:
    """Load audio from raw bytes → mono float32, resampled to target_sr."""
    with io.BytesIO(audio_bytes) as buf:
        audio, sr = sf.read(buf, dtype="float32", always_2d=False)

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sr != target_sr:
        g = gcd(sr, target_sr)
        audio = resample_poly(audio, target_sr // g, sr // g)

    return audio.astype(np.float32), target_sr


def audio_to_bytes(audio: np.ndarray, sample_rate: int, fmt: str = "WAV") -> bytes:
    """Encode float32 numpy array → WAV bytes."""
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format=fmt, subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def pcm_bytes_to_array(pcm_bytes: bytes, dtype: str = "float32") -> np.ndarray:
    return np.frombuffer(pcm_bytes, dtype=dtype).copy()


def array_to_pcm_bytes(audio: np.ndarray) -> bytes:
    return audio.astype(np.float32).tobytes()


def chunk_audio(audio: np.ndarray, chunk_samples: int) -> Generator[np.ndarray, None, None]:
    for start in range(0, len(audio), chunk_samples):
        yield audio[start: start + chunk_samples]


def normalize_audio(audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    peak = np.abs(audio).max()
    if peak > 1e-6:
        audio = audio * (target_peak / peak)
    return audio.astype(np.float32)
