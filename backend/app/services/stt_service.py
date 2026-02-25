"""
STT Service — faster-whisper via persistent subprocess.

Runs WhisperModel in an isolated child process to avoid
CTranslate2 ↔ asyncio/uvicorn OpenMP conflict on macOS.

The worker process (stt_worker_process.py) stays alive for the
lifetime of the server; audio is sent via stdin, results via stdout
using line-delimited JSON + base64 encoding.
"""
from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.config import settings
from app.utils.logging import logger

_WORKER_SCRIPT = Path(__file__).parent.parent.parent / "stt_worker_process.py"


class STTService:
    def __init__(
        self,
        model_size:   Optional[str] = None,
        device:       Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        self.model_size   = model_size   or settings.WHISPER_MODEL_SIZE
        self.device       = device       or settings.DEVICE
        self.compute_type = compute_type or settings.WHISPER_COMPUTE_TYPE
        self._proc:    Optional[subprocess.Popen] = None
        self._init_lock = threading.Lock()   # guards worker startup
        self._io_lock   = threading.Lock()   # guards stdin/stdout I/O

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Start the worker subprocess and wait for it to signal 'ready'."""
        with self._init_lock:
            if self._proc is not None and self._proc.poll() is None:
                return   # already running

            env = os.environ.copy()
            env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
            env["HF_HUB_OFFLINE"]       = "1"

            logger.info(
                f"STT: loading whisper-{self.model_size} "
                f"device={self.device} compute={self.compute_type}"
            )
            self._proc = subprocess.Popen(
                [
                    sys.executable,
                    str(_WORKER_SCRIPT),
                    self.model_size,
                    self.device,
                    self.compute_type,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,   # line-buffered
            )

            # Wait for "ready" signal (up to 60 s)
            deadline = time.time() + 60
            while time.time() < deadline:
                line = self._proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "ready":
                        logger.info("STT: model ready")
                        return
                except json.JSONDecodeError:
                    pass

            # If we get here, worker failed to start
            stderr_out = self._proc.stderr.read(2000) if self._proc.stderr else ""
            raise RuntimeError(
                f"STT worker failed to start: {stderr_out}"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def transcribe(
        self,
        audio:       np.ndarray,
        language:    Optional[str] = None,
        sample_rate: int = 16000,
    ) -> Dict:
        """
        Transcribe audio array via worker subprocess.

        Args:
            audio       : float32 numpy array, mono, 16 kHz
            language    : ISO-639-1 code or None (auto)
            sample_rate : must be 16000 for Whisper

        Returns:
            {
                "transcript": str,
                "segments":   [{start, end, text, confidence}],
                "language":   str,
                "latency_ms": float,
            }
        """
        t0 = time.time()
        self._load()   # no-op if already running; guarded by _init_lock

        with self._io_lock:
            req = {
                "audio_b64": base64.b64encode(audio.astype(np.float32).tobytes()).decode(),
                "language":  language or settings.WHISPER_LANGUAGE or "",
                "sr":        sample_rate,
            }
            try:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()

                raw = self._proc.stdout.readline()
            except (BrokenPipeError, OSError):
                self._proc = None
                raise RuntimeError("STT worker crashed; will restart on next call")

        if not raw:
            self._proc = None
            raise RuntimeError("STT worker returned empty response")

        result = json.loads(raw)
        if "error" in result:
            raise RuntimeError(f"STT worker error: {result['error']}")

        result["latency_ms"] = round((time.time() - t0) * 1000, 2)
        return result
