"""
Pipeline latency tracker.

Usage:
    m = MetricsTracker()
    m.start("session-123")
    ...
    m.record_vad(vad_result["latency_ms"])
    ...
    final = m.finish()   # PipelineMetrics dataclass
"""
from __future__ import annotations
import time
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict


@dataclass
class PipelineMetrics:
    session_id: str
    audio_duration_ms: float = 0.0
    vad_detect_ms: float = 0.0
    stt_ms: float = 0.0
    emotion_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def processing_ms(self) -> float:
        return self.vad_detect_ms + self.stt_ms + self.emotion_ms + self.tts_ms

    @property
    def rtf(self) -> float:
        """Real-Time Factor = processing_ms / audio_duration_ms (lower is better)."""
        if self.audio_duration_ms <= 0:
            return 0.0
        return self.processing_ms / self.audio_duration_ms

    def summary(self) -> str:
        return (
            f"total={self.total_ms:.0f}ms "
            f"[vad={self.vad_detect_ms:.0f} stt={self.stt_ms:.0f} "
            f"emotion={self.emotion_ms:.0f} tts={self.tts_ms:.0f}] "
            f"RTF={self.rtf:.2f}"
        )


class MetricsTracker:
    def __init__(self, log_path: str = "logs/metrics.jsonl"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self._current: Optional[PipelineMetrics] = None
        self._wall_start: float = 0.0

    # ── Record ───────────────────────────────────────────────────────────────

    def start(self, session_id: str) -> "MetricsTracker":
        self._current = PipelineMetrics(session_id=session_id)
        self._wall_start = time.time()
        return self

    def record_audio_duration(self, ms: float) -> None:
        if self._current:
            self._current.audio_duration_ms = ms

    def record_vad(self, ms: float) -> None:
        if self._current:
            self._current.vad_detect_ms = ms

    def record_stt(self, ms: float) -> None:
        if self._current:
            self._current.stt_ms = ms

    def record_emotion(self, ms: float) -> None:
        if self._current:
            self._current.emotion_ms = ms

    def record_tts(self, ms: float) -> None:
        if self._current:
            self._current.tts_ms = ms

    def finish(self) -> Optional[PipelineMetrics]:
        if self._current is None:
            return None
        self._current.total_ms = (time.time() - self._wall_start) * 1000
        self._persist(self._current)
        result = self._current
        self._current = None
        return result

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist(self, m: PipelineMetrics) -> None:
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(asdict(m)) + "\n")
        except Exception:
            pass  # non-fatal

    def load_history(self) -> List[Dict]:
        try:
            with open(self.log_path) as f:
                return [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def summary_stats(self) -> Dict:
        history = self.load_history()
        if not history:
            return {}
        keys = ["vad_detect_ms", "stt_ms", "emotion_ms", "tts_ms", "total_ms"]
        stats = {}
        for k in keys:
            vals = [h[k] for h in history if k in h]
            if vals:
                stats[k] = {
                    "n": len(vals),
                    "mean": round(sum(vals) / len(vals), 1),
                    "min": round(min(vals), 1),
                    "max": round(max(vals), 1),
                }
        return stats


# Module-level singleton for convenience
metrics_tracker = MetricsTracker()
