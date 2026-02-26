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
import re
from typing import List, Optional

import httpx

from app.utils.logging import logger

# ── Post-processing ───────────────────────────────────────────────────────────
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')  # Chinese characters

def _clean_response(text: str, reply_language: str) -> str:
    """Remove Chinese characters from Korean/English responses."""
    if reply_language in ("ko", "en"):
        text = _CJK_RE.sub('', text)
        # Collapse multiple spaces left by removal
        text = re.sub(r'  +', ' ', text).strip()
    return text
from app.services.response_generator import generate_response
from app.services.web_search import search_if_needed

# ── Prompt ───────────────────────────────────────────────────────────────────
# Full system prompts per language — written in the target language to avoid
# translation-style artifacts in the model output.
# {name} placeholder is filled in _get_system_prompt().

_SYSTEM_PROMPTS: dict = {
    "ko": (
        "당신은 {name}이에요. 친한 친구처럼 자연스럽고 따뜻하게 대화해요. "
        "상대방이 한 말에 구체적으로 반응하세요. 공감하거나 가볍게 물어보거나 한마디 던지세요. "
        "절대 하지 말 것: '네,', '아,', '어떻게 도와드릴까요?', '무엇을 도와드릴까요?' 로 시작하기. "
        "자연스러운 한국어 존댓말을 일관되게 쓰세요. 한자·영어·외국어 절대 금지. 번역체 표현 금지. "
        "1~2문장으로 짧게 답하세요. 이모지나 특수기호 사용 금지. "
        "[실시간 날씨] 태그가 있으면 내용을 자연스럽게 녹여 말하고 태그는 출력하지 마세요. "
        "모르는 정보는 모른다고 솔직하게 말하세요."
    ),
    "en": (
        "You are {name}, a friendly AI companion. Talk like a close friend — natural, warm, casual. "
        "React specifically to what was just said. Empathize, ask a follow-up, or make a light comment. "
        "Never start with 'Sure!', 'Of course!', 'How can I help?', or 'Great!'. "
        "Reply in natural English only. No other languages. "
        "1-2 sentences max. No emojis, no special symbols. "
        "If [실시간 날씨] tag appears, use that weather info naturally without showing the tag. "
        "If you don't know something, say so honestly."
    ),
    "ja": (
        "あなたは{name}です。親しい友達のように自然で温かく話してください。"
        "相手が言ったことに具体的に反応してください。共感したり、軽く質問したりしてください。"
        "「はい、」「もちろん」「何かお手伝いできますか？」で始めないでください。"
        "自然な日本語のみで返答してください。他の言語は混ぜないでください。"
        "1〜2文で短く答えてください。絵文字や特殊記号は使わないでください。"
        "[실시간 날씨]タグがあれば内容を自然に使い、タグ自体は出力しないでください。"
    ),
    "zh": (
        "你是{name}，像亲密朋友一样自然温暖地交谈。"
        "直接回应对方说的内容，表示共情或轻松地问一句。"
        "不要用'好的，''当然，''我能帮你什么？'开头。"
        "只用自然的中文回复，不要混入其他语言。"
        "回答1-2句话，简短。不要使用表情符号或特殊符号。"
        "如果出现[실시간 날씨]标签，自然地融入内容，不要输出标签本身。"
    ),
}

def _get_system_prompt(reply_language: str, character_name: str) -> str:
    template = _SYSTEM_PROMPTS.get(reply_language, _SYSTEM_PROMPTS["en"])
    return template.format(name=character_name)

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
    reply_language: str = "ko",
    character_name: str = "유나",
) -> str:
    """
    Returns an AI response string.
    Tries: Ollama → Anthropic → template fallback.
    Web search results are injected into the transcript when relevant.
    """
    # 0. Web search — inject results into transcript if needed
    if transcript:
        web_result = await search_if_needed(transcript)
        if web_result:
            transcript = f"{transcript}\n{web_result}"
            logger.info(f"Web: injected search result into context")

    # 1. Ollama (local)
    try:
        text = await _try_ollama(transcript, emotion_label, intensity, conversation_history, reply_language, character_name)
        if text:
            text = _clean_response(text, reply_language)
            logger.info(f"LLM: Ollama response ({len(text)} chars)")
            return text
    except Exception as e:
        logger.debug(f"LLM: Ollama unavailable — {e}")

    # 2. Anthropic Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        try:
            text = await _try_anthropic(transcript, emotion_label, intensity, conversation_history, api_key, reply_language, character_name)
            if text:
                text = _clean_response(text, reply_language)
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
    reply_language: str = "ko",
    character_name: str = "유나",
) -> Optional[str]:
    messages = _build_messages(transcript, emotion_label, intensity, history, include_system=True, reply_language=reply_language, character_name=character_name)

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model":      "qwen2.5:1.5b",
                "messages":   messages,
                "stream":     False,
                "keep_alive": -1,
                "options": {
                    "num_predict": 60,   # 1-2 sentences ≈ 40-60 tokens
                    "num_ctx":     512,  # small context window → faster prefill
                    "temperature": 0.7,
                },
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip() or None


async def _try_anthropic(
    transcript: str,
    emotion_label: str,
    intensity: float,
    history: Optional[List[dict]],
    api_key: str,
    reply_language: str = "ko",
    character_name: str = "유나",
) -> Optional[str]:
    # Anthropic does not accept system role inside messages
    messages = _build_messages(transcript, emotion_label, intensity, history, include_system=False, reply_language=reply_language, character_name=character_name)
    system = _get_system_prompt(reply_language, character_name)

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
                "max_tokens": 150,
                "system": system,
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
    reply_language: str = "ko",
    character_name: str = "유나",
) -> List[dict]:
    messages: List[dict] = []

    if include_system:
        messages.append({"role": "system", "content": _get_system_prompt(reply_language, character_name)})

    # Last 2 history items (1 turn) — minimized for speed
    if history:
        messages.extend(history[-2:])

    emotion_kr = _EMOTION_KR.get(emotion_label, emotion_label)
    intensity_pct = int(intensity * 100)
    content = f"[감정: {emotion_kr} {intensity_pct}%] {transcript}" if transcript else f"[감정: {emotion_kr} {intensity_pct}%] (무음)"
    messages.append({"role": "user", "content": content})

    return messages
