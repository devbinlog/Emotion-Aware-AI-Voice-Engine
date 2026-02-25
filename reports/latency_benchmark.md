# Latency Benchmark

## Measurement Method

End-to-end wall clock — WebSocket `end_stream` 수신부터 마지막 `audio_chunk` 전송까지.

```
t_start  = WS "end_stream" 수신 시점
t_vad    = vad.detect() 완료 후
t_stt    = stt.transcribe() 완료 후
t_emo    = emotion.analyze() 완료 후
t_llm    = llm 응답 생성 완료 후   ← 추가됨
t_tts    = tts.synthesize() 완료 후

vad_ms     = t_vad  - t_start
stt_ms     = t_stt  - t_vad
emotion_ms = t_emo  - t_stt
llm_ms     = t_llm  - t_emo       ← LLM 응답 생성
tts_ms     = t_tts  - t_llm
total_ms   = t_tts  - t_start
```

결과는 `logs/metrics.jsonl`에 누적, `GET /api/metrics`로 조회.

---

## 현재 구성 (macOS, Apple M1, CPU-only)

| 컴포넌트 | 설정 |
|----------|------|
| TTS | macOS say (Yuna, ko_KR) |
| STT | faster-whisper tiny, int8 (서브프로세스) |
| LLM | 템플릿 폴백 (Ollama/Claude 없을 때) |
| VAD | silero-vad (lazy load) |

### 측정 결과 (2초 입력)

| 단계 | p50 (ms) | p95 (ms) |
|------|:--------:|:--------:|
| VAD | 10 | 15 |
| STT (tiny) | 180 | 250 |
| Emotion | 55 | 80 |
| LLM (템플릿) | <1 | <1 |
| TTS (say) | 380 | 520 |
| 합계 | ~630 | ~870 |

### 측정 결과 (5초 입력)

| 단계 | p50 (ms) | p95 (ms) |
|------|:--------:|:--------:|
| VAD | 20 | 30 |
| STT (tiny) | 290 | 380 |
| Emotion | 75 | 110 |
| LLM (템플릿) | <1 | <1 |
| TTS (say) | 480 | 640 |
| 합계 | ~870 | ~1,160 |

---

## 레거시 측정 — Coqui VITS (참조용)

### 2초 입력 (Apple M2, Coqui VITS)

| 단계 | p50 (ms) | p95 (ms) |
|------|:--------:|:--------:|
| VAD | 12 | 18 |
| STT (small) | 420 | 510 |
| Emotion | 310 | 390 |
| TTS (VITS) | 950 | 1,250 |
| 합계 | 1,720 | 2,200 |

---

## LLM 추가 시 지연 예상

| LLM 엔진 | 응답 생성 지연 | 총 지연 영향 |
|----------|:------------:|:----------:|
| 템플릿 | <1ms | 무시 가능 |
| Ollama (llama3.2, CPU) | ~800–2,000ms | +1,000ms |
| Anthropic Claude Haiku | ~300–800ms | +500ms |
| Anthropic Claude Sonnet | ~500–1,500ms | +1,000ms |

> LLM 사용 시 총 지연이 크게 증가함. 실시간성이 중요하면 경량 템플릿 폴백 권장.

---

## 병목 분석 (현재 구성, 2초 입력)

```
TTS (say)  ████████████████████████  60%  ← 주 병목
STT (tiny) █████████████            28%
Emotion    ████                      9%
VAD        ▌                         2%
Overhead   ▌                         1%
```

---

## 최적화 경로

| 우선순위 | 액션 | 예상 효과 |
|----------|------|-----------|
| 1 | STT `base` 모델로 전환 (정확도↑) | WER 22%→16%, +170ms |
| 2 | LLM 응답을 비동기 프리패치 (TTS와 병렬화) | LLM 지연 숨김 가능 |
| 3 | Piper TTS (ONNX) 전환 | TTS: ~380ms → ~150ms |
| 4 | 스트리밍 STT 부분 텍스트 | 첫 단어 출력 지연↓ |
| 5 | GPU 도입 (XTTS v2) | 한국어 고품질 + <500ms |
