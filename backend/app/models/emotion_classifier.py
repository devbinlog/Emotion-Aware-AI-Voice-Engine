"""
Emotion Classifier — rule-based baseline, replaceable interface.

Design contract:
  classify_audio(features: Dict) → EmotionResult
  classify_text(text: str)       → EmotionResult
  load_custom(path: str)         → (override to load ML model)

Both methods return the same EmotionResult schema so the fusion layer is
agnostic to which backend is running.

EmotionResult = {
    "emotion_label": str,          # one of LABELS
    "intensity": float,            # 0.0 – 1.0 (confidence of top class)
    "probabilities": Dict[str, float],  # sum ≈ 1.0
}

Replacement targets:
  - classify_audio  → ECAPA-TDNN / SER model (e.g., speechbrain)
  - classify_text   → KoBERT / klue-bert-base fine-tuned on MAST / KEmotionBERT
"""
from __future__ import annotations
from typing import Dict, List, Optional

LABELS: List[str] = ["neutral", "happy", "sad", "angry", "excited", "calm"]


def _normalize(probs: Dict[str, float]) -> Dict[str, float]:
    total = sum(probs.values())
    if total < 1e-9:
        return {k: (1.0 / len(LABELS)) for k in LABELS}
    return {k: v / total for k, v in probs.items()}


def _best(probs: Dict[str, float]) -> tuple[str, float]:
    label = max(probs, key=probs.get)
    return label, round(probs[label], 4)


# ── Text keyword lexicon ──────────────────────────────────────────────────────
# MVP: heuristic scoring; swap with KoBERT/klue-bert by overriding classify_text.
_TEXT_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "기뻐", "기쁘", "좋아", "행복", "감사", "웃", "즐거", "신나", "사랑",
        "happy", "joy", "great", "wonderful", "love", "glad", "cheerful",
    ],
    "sad": [
        "슬프", "우울", "힘들", "외로", "눈물", "그리워", "괴로", "아프",
        "sad", "cry", "miss", "lonely", "depressed", "sorrow", "grief",
    ],
    "angry": [
        "화나", "짜증", "열받", "싫어", "분노", "억울", "황당",
        "angry", "hate", "mad", "furious", "frustrated", "annoyed", "upset",
    ],
    "excited": [
        "흥분", "설레", "두근", "기대", "와우", "대박", "놀라",
        "excited", "wow", "amazing", "awesome", "thrilled", "incredible",
    ],
    "calm": [
        "평온", "차분", "괜찮", "안정", "편안", "조용",
        "calm", "peace", "relax", "okay", "fine", "quiet", "serene",
    ],
}


class EmotionClassifier:
    """
    Rule-based emotion classifier.

    Audio branch: hand-crafted prosody feature → emotion heuristics.
    Text branch:  keyword lexicon scoring.
    Both branches output probabilities over LABELS for fusion.
    """

    # ── Audio prosody → emotion ───────────────────────────────────────────────
    # Heuristic thresholds (calibrated on general speech; replace with trained model).
    # Feature ranges (16kHz mono speech):
    #   f0_mean : ~80–300 Hz   (higher = more energy/excitement)
    #   rms_mean: ~0.01–0.15   (higher = louder)
    #   zcr_mean: ~0.05–0.25   (higher = more fricatives/noise)
    #   f0_std  : ~10–80 Hz    (higher = more pitch variation)
    #   speaking_rate: onsets/sec ~1–8

    def classify_audio(self, features: Dict) -> Dict:
        """
        Map prosody features to emotion probabilities.

        Scoring logic:
          Each rule adds weight to one or more emotion buckets.
          Weights accumulate; final probs are L1-normalized.
          F0=0 means autocorrelation found no voiced frame — fall back to
          RMS/ZCR/rate only (prevents always-neutral when F0 detection fails).
        """
        probs: Dict[str, float] = {k: 0.0 for k in LABELS}
        probs["neutral"] = 0.10  # lower baseline — easier for other emotions to win

        f0_mean       = features.get("f0_mean",      0.0)
        f0_std        = features.get("f0_std",        0.0)
        rms_mean      = features.get("rms_mean",      0.05)
        zcr_mean      = features.get("zcr_mean",      0.10)
        speaking_rate = features.get("speaking_rate",  3.0)

        # Use default F0 if autocorrelation returned 0 (no voiced frames)
        f0_reliable = f0_mean > 50.0
        if not f0_reliable:
            f0_mean = 150.0   # assume neutral pitch; let RMS/ZCR drive result
            f0_std  = 25.0

        # ── Rule set (thresholds relaxed for real-world microphone input) ────

        # R1: High pitch + energy + fast rate → excited
        if f0_mean > 185 and rms_mean > 0.06 and speaking_rate > 3.5:
            probs["excited"] += 0.55
            probs["happy"]   += 0.20

        # R2: Moderately high pitch + moderate energy → happy
        elif f0_mean > 155 and rms_mean > 0.04:
            probs["happy"]   += 0.45
            probs["excited"] += 0.10

        # R3: High energy OR high ZCR + pitch variance → angry
        if rms_mean > 0.07 and (zcr_mean > 0.12 or f0_std > 35):
            probs["angry"]   += 0.50

        # R4: Low pitch + low energy + slow rate → sad
        if f0_mean < 140 and rms_mean < 0.05 and speaking_rate < 3.0:
            probs["sad"]     += 0.45

        # R5: Low energy + stable pitch + moderate rate → calm
        if rms_mean < 0.06 and f0_std < 28 and 2.0 < speaking_rate < 4.5:
            probs["calm"]    += 0.35

        # R6: Very low energy (whisper/quiet) → calm
        if rms_mean < 0.03:
            probs["calm"]    += 0.25

        # R7: Fast speech with high energy (without high pitch) → excited/happy
        if speaking_rate > 4.5 and rms_mean > 0.05:
            probs["excited"] += 0.20
            probs["happy"]   += 0.10

        probs = _normalize(probs)
        label, intensity = _best(probs)
        return {"emotion_label": label, "intensity": intensity, "probabilities": probs}

    # ── Text sentiment → emotion ──────────────────────────────────────────────

    def classify_text(self, text: str) -> Dict:
        """
        Keyword-count scoring over bilingual (KO/EN) lexicon.

        Replacement: implement the same signature with KoBERT or any
        HuggingFace model, return identical Dict schema.
        """
        text_lower = text.lower()
        probs: Dict[str, float] = {k: 0.0 for k in LABELS}
        probs["neutral"] = 0.10  # baseline

        for emotion, keywords in _TEXT_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    probs[emotion] += 1.0

        probs = _normalize(probs)
        label, intensity = _best(probs)
        return {"emotion_label": label, "intensity": intensity, "probabilities": probs}

    # ── Extension hook ────────────────────────────────────────────────────────

    def load_custom(self, model_path: str) -> None:
        """
        Override to load an ML model (e.g., sklearn pkl, torch checkpoint).
        After loading, override classify_audio / classify_text as needed.
        """
        raise NotImplementedError("Implement load_custom for ML backend.")
