"""
Emotion-Aware AI Voice Engine — FastAPI entry point.

Start:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")       # use local cache, no HF network calls
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # suppress OpenMP duplicate warning
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.api.websocket import ws_router
from app.utils.logging import setup_logging
from app.utils.logging import logger

setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title       = "Emotion-Aware AI Voice Engine",
    version     = "0.1.0",
    description = (
        "MVP pipeline: Voice → VAD → STT → Emotion Analysis → "
        "Emotion-Conditioned TTS → Streaming Audio Response"
    ),
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(router,    prefix="/api",  tags=["Pipeline"])
app.include_router(ws_router,                 tags=["WebSocket"])


# ── Startup: pre-warm models ─────────────────────────────────────────────────
@app.on_event("startup")
async def _warmup():
    # 1. STT worker subprocess (runs in thread to avoid blocking event loop)
    try:
        from app.api.websocket import _services
        await asyncio.to_thread(lambda: _services()[1]._load())
        logger.info("STT: worker pre-loaded")
    except Exception as e:
        logger.debug(f"STT: warmup skipped — {e}")

    # 2. Ollama LLM
    try:
        import httpx
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model":      "qwen2.5:1.5b",
                    "messages":   [{"role": "user", "content": "안녕"}],
                    "stream":     False,
                    "keep_alive": -1,
                    "options":    {"num_predict": 20},
                },
            )
            if resp.status_code == 200:
                logger.info("LLM: Ollama warmed up")
    except Exception as e:
        logger.debug(f"LLM: Ollama warmup skipped — {e}")


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    try:
        import torch
        gpu = torch.cuda.is_available()
    except ImportError:
        gpu = False
    return {
        "status": "ok",
        "device": settings.DEVICE,
        "gpu":    gpu,
        "tts_engine": settings.TTS_ENGINE,
        "whisper_model": settings.WHISPER_MODEL_SIZE,
    }
