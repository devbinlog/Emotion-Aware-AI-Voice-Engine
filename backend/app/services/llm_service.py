"""
LLM Conversation Service.

Fallback chain:
  1. Ollama  (http://localhost:11434)  — free, local
  2. Anthropic Claude API              — if ANTHROPIC_API_KEY env var is set
  3. Template responses                — always available

Conversation history is maintained per WebSocket session (list of
{"role": "user"/"assistant", "content": str} dicts, last 8 messages).
"""
from __future__ import annotations

import os
from typing import List, Optional

import httpx

from app.utils.logging import logger
from app.services.response_generator import generate_response

# ── Prompt ───────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "당신은 따뜻하고 공감 능력이 뛰어난 AI 음성 어시스턴트입니다. "
    "사용자의 감정 상태를 고려하여 자연스럽고 진심 어린 한국어로 대화합니다. "
    "답변은 2~3문장 이내로 간결하게 해주세요. "
    "이모지나 특수 기호는 사용하지 않습니다."
)

_EMOTION_KR = {
    "happy":   "행복",
    "sad":     "슬픔",
    "angry":   "분노",
    "excited": "흥분",
    "calm":    "차분",
    "neutral": "중립",
}

# ── Public API ────────────────────────────────────────────────────────────────

async def get_llm_response(
    transcript: str,
    emotion_label: str,
    intensity: float,
    conversation_history: Optional[List[dict]] = None,
) -> str:
    """
    Returns an AI response string.
    Tries: Ollama → Anthropic → template fallback.
    """
    # 1. Ollama (local)
    try:
        text = await _try_ollama(transcript, emotion_label, intensity, conversation_history)
        if text:
            logger.info(f"LLM: Ollama response ({len(text)} chars)")
            return text
    except Exception as e:
        logger.debug(f"LLM: Ollama unavailable — {e}")

    # 2. Anthropic Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        try:
            text = await _try_anthropic(transcript, emotion_label, intensity, conversation_history, api_key)
            if text:
                logger.info(f"LLM: Anthropic response ({len(text)} chars)")
                return text
        except Exception as e:
            logger.warning(f"LLM: Anthropic API failed — {e}")

    # 3. Template fallback
    logger.info("LLM: using template fallback")
    return generate_response(emotion_label, transcript, intensity)


# ── Backends ──────────────────────────────────────────────────────────────────

async def _try_ollama(
    transcript: str,
    emotion_label: str,
    intensity: float,
    history: Optional[List[dict]],
) -> Optional[str]:
    messages = _build_messages(transcript, emotion_label, intensity, history, include_system=True)

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "http://localhost:11434/api/chat",
            json={"model": "llama3.2", "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip() or None


async def _try_anthropic(
    transcript: str,
    emotion_label: str,
    intensity: float,
    history: Optional[List[dict]],
    api_key: str,
) -> Optional[str]:
    # Anthropic does not accept system role inside messages
    messages = _build_messages(transcript, emotion_label, intensity, history, include_system=False)

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system": _SYSTEM_PROMPT,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip() or None


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_messages(
    transcript: str,
    emotion_label: str,
    intensity: float,
    history: Optional[List[dict]],
    include_system: bool,
) -> List[dict]:
    messages: List[dict] = []

    if include_system:
        messages.append({"role": "system", "content": _SYSTEM_PROMPT})

    # Last 6 history items (3 turns)
    if history:
        messages.extend(history[-6:])

    emotion_kr = _EMOTION_KR.get(emotion_label, emotion_label)
    intensity_pct = int(intensity * 100)
    content = f"[감정: {emotion_kr} {intensity_pct}%] {transcript}" if transcript else f"[감정: {emotion_kr} {intensity_pct}%] (무음)"
    messages.append({"role": "user", "content": content})

    return messages
