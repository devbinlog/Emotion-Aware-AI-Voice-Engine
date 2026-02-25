"""
Emotion-aware response generator.

Produces a varied Korean reply based on the detected emotion + transcript.
No LLM needed — uses curated response templates per emotion class.
Randomly selects from multiple templates to avoid repetition.
"""
from __future__ import annotations
import random
from typing import Optional

# ── Response templates per emotion ───────────────────────────────────────────
_TEMPLATES: dict[str, list[str]] = {
    "happy": [
        "정말 기분이 좋아 보여요! 저도 덩달아 기분이 밝아지네요.",
        "와, 행복한 에너지가 느껴져요! 좋은 일이 있으셨나 봐요.",
        "그 밝은 기분이 저한테도 전해져요. 오늘 하루도 즐겁게 보내세요!",
        "기쁜 소식인가요? 함께 기뻐할게요!",
    ],
    "excited": [
        "와! 정말 신나 보여요! 무슨 일이에요?",
        "그 흥분된 목소리가 느껴져요! 저도 두근두근하네요.",
        "엄청난 에너지네요! 좋은 일이 생긴 것 같아요.",
        "오, 뭔가 굉장히 기대되는 일이 있나봐요!",
    ],
    "sad": [
        "힘드신가요? 제가 옆에서 들을게요.",
        "많이 지치셨겠어요. 오늘 하루도 수고하셨어요.",
        "그런 감정도 괜찮아요. 잠깐 쉬어가는 것도 좋아요.",
        "마음이 많이 무거워 보여요. 조금이라도 위로가 되길 바라요.",
    ],
    "angry": [
        "많이 답답하고 화나셨겠어요. 충분히 이해해요.",
        "그럴 수 있죠. 잠깐 심호흡 한번 해볼까요?",
        "화가 나는 건 당연해요. 차분하게 이야기해요.",
        "그 감정 충분히 받아들일게요.",
    ],
    "calm": [
        "차분하고 안정적인 느낌이 좋아요.",
        "평온한 목소리네요. 덕분에 저도 마음이 편안해져요.",
        "여유로운 분위기가 전해져요. 좋은 하루 되세요.",
        "안정감이 느껴져요. 오늘 하루도 편안하게 보내세요.",
    ],
    "neutral": [
        "네, 잘 들었어요.",
        "말씀 잘 들었습니다.",
        "알겠어요. 더 이야기해 주세요.",
        "네, 계속 말씀해 주세요.",
    ],
}

# If transcript is not empty, prepend a short acknowledgement
_ACK_TEMPLATES: dict[str, list[str]] = {
    "happy":   ["그렇군요! ", "오, 정말요? ", "좋겠어요! "],
    "excited": ["우와! ", "정말요?! ", "대박이에요! "],
    "sad":     ["그랬군요... ", "그러셨어요. ", ""],
    "angry":   ["그렇군요. ", "이해해요. ", ""],
    "calm":    ["네, ", "그렇군요. ", ""],
    "neutral": ["", "네. ", ""],
}


def generate_response(
    emotion_label: str,
    transcript: Optional[str] = None,
    intensity: float = 0.5,
) -> str:
    """
    Generate an emotion-conditioned AI response.

    Args:
        emotion_label: detected emotion
        transcript:    user's spoken text (can be empty)
        intensity:     0–1 emotion strength

    Returns:
        Korean response string
    """
    label = emotion_label if emotion_label in _TEMPLATES else "neutral"
    base  = random.choice(_TEMPLATES[label])

    # If there's a transcript and intensity is strong enough, prepend acknowledgement
    if transcript and intensity > 0.4:
        ack = random.choice(_ACK_TEMPLATES.get(label, [""]))
        return ack + base

    return base
