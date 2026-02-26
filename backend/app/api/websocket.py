"""
WebSocket voice pipeline: /ws/voice

Protocol (text frames, JSON):
──────────────────────────────────────────────────────────────────────────────
Client → Server
  { "type": "config",       "language": "ko", "speaker": null }
  { "type": "audio_chunk",  "data": "<base64 float32 PCM>", "sample_rate": 16000 }
  { "type": "end_stream",   "sample_rate": 16000 }

Server → Client
  { "type": "ack",             "config": {...} }
  { "type": "vad_event",       "speech_detected": bool, "confidence": float }
  { "type": "final_transcript","text": str, "language": str }
  { "type": "emotion",         "emotion_label": str, "intensity": float,
                               "probabilities": {...}, "features_summary": {...} }
  { "type": "audio_chunk",     "data": "<base64 WAV bytes>",
                               "sample_rate": int, "is_last": bool }
  { "type": "metrics",         "vad_ms": f, "stt_ms": f, "emotion_ms": f,
                               "tts_ms": f, "total_ms": f }
  { "type": "error",           "message": str }
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import asyncio
import base64
import json
import subprocess
import time
import uuid
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.audio_io import audio_to_bytes
from app.services.vad_service import VADService
from app.services.stt_service import STTService
from app.services.emotion_service import EmotionService
from app.services.tts_service import TTSService
from app.services.llm_service import get_llm_response
from app.utils.metrics import MetricsTracker
from app.utils.logging import logger
from app.config import settings

ws_router = APIRouter()

# ── Voice → reply language ────────────────────────────────────────────────────
_VOICE_LANG: dict = {
    "Yuna": "ko",
    "Kyoko": "ja",
    "Meijia": "zh", "Tingting": "zh", "Sinji": "zh",
}

# ── Voice → character name (shown in LLM identity) ────────────────────────────
_VOICE_NAME: dict = {
    "Yuna":     "유나",
    "Kyoko":    "Kyoko",
    "Meijia":   "Meijia",
    "Tingting": "Tingting",
    "Sinji":    "Sinji",
}

def _voice_reply_lang(voice: str) -> str:
    """Return ISO language code for the given TTS voice name."""
    return _VOICE_LANG.get(voice, "en")

def _voice_character_name(voice: str) -> str:
    """Return character name for the given TTS voice name."""
    return _VOICE_NAME.get(voice, voice)  # fallback: use voice name as-is


def _ffmpeg_decode(webm_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    """Decode WebM/Opus bytes → float32 PCM at target_sr using ffmpeg."""
    proc = subprocess.run(
        [
            'ffmpeg', '-y',
            '-i', 'pipe:0',
            '-f', 'f32le',
            '-ar', str(target_sr),
            '-ac', '1',
            'pipe:1',
        ],
        input=webm_bytes,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.decode()[:400]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()

# ── Service singletons (shared across sessions) ──────────────────────────────
_vad:     Optional[VADService]     = None
_stt:     Optional[STTService]     = None
_emotion: Optional[EmotionService] = None
_tts:     Optional[TTSService]     = None


def _services():
    global _vad, _stt, _emotion, _tts
    _vad     = _vad     or VADService()
    _stt     = _stt     or STTService()
    _emotion = _emotion or EmotionService()
    _tts     = _tts     or TTSService()
    return _vad, _stt, _emotion, _tts


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


# ── WebSocket handler ────────────────────────────────────────────────────────

@ws_router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    await ws.accept()
    sid = str(uuid.uuid4())[:8]
    logger.info(f"[WS {sid}] connected")

    vad, stt, emotion, tts = _services()
    metrics = MetricsTracker(settings.METRICS_LOG_PATH)

    audio_buffer: List[np.ndarray] = []
    conversation_history: List[dict] = []          # LLM conversation memory
    config = {
        "language": settings.WHISPER_LANGUAGE,
        "speaker":  None,
        "voice":    settings.TTS_SAY_VOICE,   # TTS voice (macOS say)
    }

    try:
        async for raw in ws.iter_text():
            msg = json.loads(raw)
            t   = msg.get("type")

            # ── config ───────────────────────────────────────────────────────
            if t == "config":
                for k in ("language", "speaker", "voice"):
                    if k in msg:
                        config[k] = msg[k]
                # Restore conversation history from client (multi-turn across WS sessions)
                if "history" in msg and isinstance(msg.get("history"), list):
                    conversation_history.clear()
                    conversation_history.extend(msg["history"][-20:])
                    logger.info(f"[WS {sid}] restored {len(conversation_history)} history messages")
                await _send(ws, {"type": "ack", "config": config})

            # ── audio_chunk ──────────────────────────────────────────────────
            elif t == "audio_chunk":
                raw_data = msg.get("data", "")
                if not raw_data:
                    continue

                encoding = msg.get("encoding", "pcm")
                if encoding == "webm":
                    webm_bytes = base64.b64decode(raw_data)
                    chunk = await asyncio.to_thread(_ffmpeg_decode, webm_bytes, 16000)
                else:
                    chunk = np.frombuffer(base64.b64decode(raw_data), dtype=np.float32).copy()

                audio_buffer.append(chunk)

                # Real-time VAD on each incoming chunk
                if len(chunk) >= 512:
                    is_speech, conf = vad.is_speech_chunk(chunk[:512])
                    await _send(ws, {
                        "type":             "vad_event",
                        "speech_detected":  bool(is_speech),
                        "confidence":       conf,
                    })

            # ── end_stream ───────────────────────────────────────────────────
            elif t == "end_stream":
                if not audio_buffer:
                    await _send(ws, {"type": "error", "message": "No audio received."})
                    continue

                metrics.start(sid)
                sr      = int(msg.get("sample_rate", settings.VAD_SAMPLING_RATE))
                full    = np.concatenate(audio_buffer).astype(np.float32)
                audio_buffer.clear()
                metrics.record_audio_duration(len(full) / sr * 1000)

                rms = float(np.sqrt(np.mean(full ** 2))) if len(full) > 0 else 0.0
                logger.info(f"[WS {sid}] audio: duration={len(full)/sr:.2f}s samples={len(full)} rms={rms:.4f}")

                # 1 ── VAD (full-audio segment detection)
                t0 = time.time()
                vad_result = vad.detect(full)
                metrics.record_vad((time.time() - t0) * 1000)

                # 2 ── STT
                t0 = time.time()
                stt_result = await asyncio.to_thread(
                    stt.transcribe, full, config["language"], sr
                )
                metrics.record_stt((time.time() - t0) * 1000)
                logger.info(f"[WS {sid}] transcript='{stt_result['transcript']}' lang={stt_result['language']}")

                await _send(ws, {
                    "type":     "final_transcript",
                    "text":     stt_result["transcript"],
                    "language": stt_result["language"],
                    "segments": stt_result["segments"],
                })

                # 3 ── Emotion
                t0 = time.time()
                emo = emotion.analyze(full, sr=sr, transcript=stt_result["transcript"])
                metrics.record_emotion((time.time() - t0) * 1000)

                await _send(ws, {
                    "type":             "emotion",
                    "emotion_label":    emo["emotion_label"],
                    "intensity":        emo["intensity"],
                    "probabilities":    emo["probabilities"],
                    "features_summary": emo["features_summary"],
                })

                # 4 ── AI response (LLM with fallback) + TTS
                voice = config.get("voice", "Yuna")
                reply_lang     = _voice_reply_lang(voice)
                character_name = _voice_character_name(voice)
                ai_text = await get_llm_response(
                    transcript        = stt_result["transcript"],
                    emotion_label     = emo["emotion_label"],
                    intensity         = emo["intensity"],
                    conversation_history = conversation_history,
                    reply_language    = reply_lang,
                    character_name    = character_name,
                )
                logger.info(f"[WS {sid}] ai_response='{ai_text}'")
                await _send(ws, {"type": "ai_response", "text": ai_text})

                # Update conversation history
                emotion_kr = {"happy":"행복","sad":"슬픔","angry":"분노",
                              "excited":"흥분","calm":"차분","neutral":"중립"}.get(
                              emo["emotion_label"], emo["emotion_label"])
                conversation_history.append({
                    "role":    "user",
                    "content": f"[감정: {emotion_kr} {int(emo['intensity']*100)}%] {stt_result['transcript']}",
                })
                conversation_history.append({"role": "assistant", "content": ai_text})
                # Keep last 10 turns (20 messages) to avoid context bloat
                if len(conversation_history) > 20:
                    conversation_history[:] = conversation_history[-20:]

                t0  = time.time()
                out = tts.synthesize(
                    text          = ai_text,
                    emotion_label = emo["emotion_label"],
                    intensity     = emo["intensity"],
                    speaker       = config.get("speaker"),
                    voice         = config.get("voice"),
                )
                metrics.record_tts((time.time() - t0) * 1000)

                out_audio = out["audio"]
                out_sr    = out["sample_rate"]

                # Send entire audio as a single WAV blob.
                # Chunked WAV (each chunk with its own header) cannot be
                # concatenated on the client — only the first header is parsed.
                wav_bytes = audio_to_bytes(out_audio, out_sr)
                await _send(ws, {
                    "type":        "audio_chunk",
                    "data":        base64.b64encode(wav_bytes).decode(),
                    "sample_rate": out_sr,
                    "is_last":     True,
                })

                # 5 ── Metrics summary
                m = metrics.finish()
                if m:
                    await _send(ws, {
                        "type":       "metrics",
                        "vad_ms":     round(m.vad_detect_ms, 1),
                        "stt_ms":     round(m.stt_ms, 1),
                        "emotion_ms": round(m.emotion_ms, 1),
                        "tts_ms":     round(m.tts_ms, 1),
                        "total_ms":   round(m.total_ms, 1),
                        "rtf":        round(m.rtf, 3),
                    })
                    logger.info(f"[WS {sid}] {m.summary()}")

    except WebSocketDisconnect:
        logger.info(f"[WS {sid}] disconnected")
    except Exception as e:
        logger.error(f"[WS {sid}] error: {e}", exc_info=True)
        await _send(ws, {"type": "error", "message": str(e)})
