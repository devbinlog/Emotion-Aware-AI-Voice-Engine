"""
Emotion Service — pure numpy/scipy feature extraction (no librosa required).

Pipeline:
  audio → extract_audio_features() → Dict[feature_name, float]
        → EmotionClassifier.classify_audio → EmotionResult (audio branch)
  text  → EmotionClassifier.classify_text  → EmotionResult (text branch)
  fusion(audio, text)                       → EmotionResult (final)

Fusion: weighted sum  p_fused[c] = 0.6·p_audio[c] + 0.4·p_text[c]
Intensity: max(p_fused) after L1-normalization.
"""
from __future__ import annotations
import time
import numpy as np
from math import gcd
from scipy.fft import fft as scipy_fft
from scipy.signal import resample_poly
from typing import Dict, Optional

from app.models.emotion_classifier import EmotionClassifier, LABELS, _normalize, _best
from app.config import settings
from app.utils.logging import logger


# ── Pure numpy/scipy feature extraction ──────────────────────────────────────

def _frames(audio: np.ndarray, frame_len: int = 2048, hop: int = 512) -> np.ndarray:
    """Split signal into overlapping frames. Returns (n_frames, frame_len)."""
    n = (len(audio) - frame_len) // hop
    if n <= 0:
        return audio[np.newaxis, :]
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n)[:, None]
    return audio[idx]


def _rms(audio: np.ndarray) -> np.ndarray:
    f = _frames(audio)
    return np.sqrt(np.mean(f ** 2, axis=1))


def _zcr(audio: np.ndarray) -> np.ndarray:
    f = _frames(audio)
    return np.mean(np.abs(np.diff(np.sign(f), axis=1)) / 2, axis=1)


def _mel_filterbank(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    """Build (n_mels, n_fft//2+1) mel filterbank matrix."""
    def hz2mel(h): return 2595 * np.log10(1 + h / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)

    mel_pts = np.linspace(hz2mel(0), hz2mel(sr / 2), n_mels + 2)
    hz_pts  = mel2hz(mel_pts)
    bins    = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        lo, cen, hi = bins[m - 1], bins[m], bins[m + 1]
        for k in range(lo, cen):
            if cen > lo: fb[m - 1, k] = (k - lo) / (cen - lo)
        for k in range(cen, hi):
            if hi > cen: fb[m - 1, k] = (hi - k) / (hi - cen)
    return fb


def _mfcc(audio: np.ndarray, sr: int = 16000, n_mfcc: int = 13,
          n_mels: int = 40, n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    """Compute MFCCs — returns (n_mfcc, n_frames)."""
    frames = _frames(audio, n_fft, hop)
    if frames.shape[0] == 0:
        return np.zeros((n_mfcc, 1))

    window = np.hanning(n_fft)
    fb     = _mel_filterbank(n_mels, n_fft, sr)

    mfccs = []
    for frame in frames:
        # Pad if frame is shorter than n_fft
        f = frame if len(frame) == n_fft else np.pad(frame, (0, n_fft - len(frame)))
        power = np.abs(scipy_fft(f * window)[:n_fft // 2 + 1]) ** 2
        mel   = np.maximum(fb @ power, 1e-10)
        log_m = np.log(mel)
        # Type-III DCT via matrix multiply
        n_arr  = np.arange(n_mfcc)[:, None]
        k_arr  = np.arange(n_mels)[None, :]
        dct    = np.sum(log_m * np.cos(np.pi * n_arr * (k_arr + 0.5) / n_mels), axis=1)
        mfccs.append(dct)

    return np.array(mfccs).T  # (n_mfcc, n_frames)


def _f0_autocorr(audio: np.ndarray, sr: int = 16000,
                 fmin: float = 65.0, fmax: float = 2093.0,
                 frame_len: int = 2048, hop: int = 512) -> np.ndarray:
    """Autocorrelation-based F0 estimation. Returns voiced F0 values (Hz)."""
    min_p = max(1, int(sr / fmax))
    max_p = min(frame_len - 1, int(sr / fmin))
    frames = _frames(audio, frame_len, hop)
    f0s = []

    for frame in frames:
        frame = frame - frame.mean()
        std = frame.std()
        if std < 1e-6:
            continue
        frame /= std
        # Normalized autocorrelation
        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(corr) // 2:]
        if corr[0] < 1e-9 or max_p <= min_p:
            continue
        search  = corr[min_p:max_p]
        peak_i  = np.argmax(search) + min_p
        if corr[peak_i] / corr[0] > 0.25:
            f0s.append(sr / peak_i)

    return np.array(f0s, dtype=np.float32) if f0s else np.array([0.0], dtype=np.float32)


def _speaking_rate(audio: np.ndarray, sr: int = 16000) -> float:
    """Energy-envelope peak count / duration → rough syllable rate."""
    rms = _rms(audio)
    if len(rms) < 3:
        return 0.0
    thr  = np.mean(rms) * 0.5
    diff = np.diff(rms)
    peaks = np.where((diff[:-1] > 0) & (diff[1:] < 0) & (rms[1:-1] > thr))[0]
    duration = len(audio) / sr
    return len(peaks) / duration if duration > 0.1 else 0.0


# ── Service ──────────────────────────────────────────────────────────────────

class EmotionService:
    def __init__(self):
        self.classifier = EmotionClassifier()
        self._audio_w   = settings.EMOTION_AUDIO_WEIGHT
        self._text_w    = settings.EMOTION_TEXT_WEIGHT

    def extract_audio_features(self, audio: np.ndarray, sr: int = 16000) -> Dict:
        feats: Dict[str, float] = {}

        # F0
        try:
            f0 = _f0_autocorr(audio, sr)
            feats["f0_mean"] = float(np.nanmean(f0))
            feats["f0_std"]  = float(np.nanstd(f0))
        except Exception as e:
            logger.warning(f"F0 failed: {e}")
            feats["f0_mean"] = 0.0
            feats["f0_std"]  = 0.0

        # RMS
        rms = _rms(audio)
        feats["rms_mean"] = float(np.mean(rms))
        feats["rms_std"]  = float(np.std(rms))

        # ZCR
        zcr = _zcr(audio)
        feats["zcr_mean"] = float(np.mean(zcr))

        # MFCCs
        try:
            mfcc = _mfcc(audio, sr)
            for i in range(min(13, mfcc.shape[0])):
                feats[f"mfcc_{i+1}_mean"] = float(np.mean(mfcc[i]))
        except Exception as e:
            logger.warning(f"MFCC failed: {e}")
            for i in range(13):
                feats[f"mfcc_{i+1}_mean"] = 0.0

        # Speaking rate
        feats["speaking_rate"] = _speaking_rate(audio, sr)

        return feats

    def fuse(self, audio_result: Dict, text_result: Optional[Dict] = None) -> Dict:
        if text_result is None:
            return audio_result

        a_probs = audio_result.get("probabilities", {})
        t_probs = text_result.get("probabilities",  {})

        fused = {
            c: self._audio_w * a_probs.get(c, 0.0) + self._text_w * t_probs.get(c, 0.0)
            for c in LABELS
        }
        fused = _normalize(fused)
        label, intensity = _best(fused)
        return {"emotion_label": label, "intensity": intensity, "probabilities": fused}

    def analyze(self, audio: np.ndarray, sr: int = 16000,
                transcript: Optional[str] = None) -> Dict:
        t0 = time.time()

        feats        = self.extract_audio_features(audio, sr)
        audio_result = self.classifier.classify_audio(feats)

        text_result: Optional[Dict] = None
        if transcript and transcript.strip():
            text_result = self.classifier.classify_text(transcript)

        fused      = self.fuse(audio_result, text_result)
        latency_ms = (time.time() - t0) * 1000

        return {
            **fused,
            "features_summary": {
                "f0_mean":       round(feats.get("f0_mean", 0.0), 2),
                "f0_std":        round(feats.get("f0_std",  0.0), 2),
                "rms_mean":      round(feats.get("rms_mean", 0.0), 4),
                "zcr_mean":      round(feats.get("zcr_mean", 0.0), 4),
                "speaking_rate": round(feats.get("speaking_rate", 0.0), 2),
            },
            "branches":   {"audio": audio_result, "text": text_result},
            "latency_ms": round(latency_ms, 2),
        }
