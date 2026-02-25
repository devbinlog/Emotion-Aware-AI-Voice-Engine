# Model & Engine Selection Rationale

## TTS Engine Comparison

| 항목 | macOS say | Coqui VITS | Piper (ONNX) | XTTS v2 |
|------|:---------:|:----------:|:------------:|:-------:|
| 설치 | 내장 (no install) | `pip install TTS` | `pip install piper-tts` + 모델 파일 | `pip install TTS` |
| CPU 지연 | ~200–500ms ⭐⭐⭐ | ~800–2,500ms ⭐⭐ | ~80–250ms ⭐⭐⭐ | ~8,000ms+ ❌ |
| 한국어 지원 | ✅ (Yuna 내장) | ✗ | ✗ (비공식만) | ✅ |
| 음성 품질 | 자연스러움 | 좋음 | 좋음 | 최고 |
| 감정 후처리 | scipy prosody ✅ | scipy prosody ✅ | scipy prosody ✅ | scipy prosody ✅ |
| CPU-only 실용성 | ✅ 최고 | ✅ 가능 | ✅ 최고 | ❌ |
| 목소리 선택 | 시스템 목소리 전체 | 단일 화자 | 모델별 화자 | 다화자 |

### 현재 설정: macOS say (Yuna)

이유:
1. 설치 불필요 — macOS 내장, 별도 pip 패키지 없음
2. 한국어 지원 — Yuna(ko_KR) 내장 음성 제공
3. 가장 빠름 — 200–500ms, CPU-only 환경에서 최고 속도
4. 목소리 선택 — `/api/voices`로 한국어/영어/일본어/중국어 음성 조회 및 변경 가능

### 엔진 교체 방법

```bash
# .env (backend/.env)
TTS_ENGINE=say       # macOS 기본 (한국어 Yuna 사용)
TTS_ENGINE=coqui     # Coqui VITS (영어, pip install TTS 필요)
TTS_ENGINE=piper     # Piper ONNX (영어, 고속)
TTS_ENGINE=xtts      # XTTS v2 (다국어, GPU 필요)
```

---

## STT: faster-whisper

현재 설정: `tiny`, int8, CPU (서브프로세스 격리)

| 모델 | CPU 지연 (5s) | WER(KO) | 크기 |
|------|:------------:|:-------:|:----:|
| tiny | ~180ms | ~22% | 39 MB |
| base | ~350ms | ~16% | 74 MB |
| small | ~700ms | ~10% | 244 MB |
| medium | ~1,800ms | ~7% | 769 MB |

tiny 선택 이유: macOS에서 CTranslate2 + asyncio 충돌 문제로 서브프로세스 격리가 필요하며, tiny 모델이 가장 빠르게 초기화되고 한국어 일상 대화에서 충분한 정확도를 보임.

> 정확도 향상이 필요하면 `WHISPER_MODEL_SIZE=small`로 변경.

### 서브프로세스 격리 구조

```
[uvicorn / asyncio]          [stt_worker_process.py]
  STTService.transcribe()  ─stdin/stdout JSON──▶  WhisperModel.transcribe()
                           ◀─ 결과 JSON ────────
```

macOS에서 CTranslate2를 asyncio 스레드 내에서 초기화하면 SIGABRT 발생 (OpenMP 충돌). 별도 프로세스 격리로 해결. 자세한 내용: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#4-파이썬-예기치-종료-팝업-sigabrt--핵심-문제)

---

## VAD: silero-vad

- `torch.hub.load` 단일 호출 — PyTorch 외 추가 패키지 없음
- ~5–15ms, ONNX 내부 최적화
- Graceful fallback: 로드 실패 시 전체 오디오를 음성으로 처리
- torch는 lazy import (서버 시작 시 로드 안 함 — SIGABRT 방지)

---

## LLM 대화 서비스

### 우선순위 체인

| 순위 | 엔진 | 조건 | 지연 |
|------|------|------|------|
| 1 | Ollama (llama3.2) | localhost:11434 동작 중 | ~500ms–2s |
| 2 | Anthropic Claude (haiku) | `ANTHROPIC_API_KEY` 설정 | ~300ms–1s |
| 3 | 템플릿 응답 | 항상 사용 가능 | <1ms |

### 멀티턴 컨텍스트

- 세션(WebSocket 연결)당 대화 히스토리 유지
- 최대 10턴(20 메시지)까지 컨텍스트 보존
- 매 턴에 감정 상태와 강도를 컨텍스트에 포함

---

## Emotion Classifier

| 단계 | 현재 구현 | 업그레이드 경로 |
|------|-----------|----------------|
| 오디오 | Prosody 규칙 기반 (F0, RMS, ZCR, MFCC) | ECAPA-TDNN / wav2vec2-emotion |
| 텍스트 | 키워드 렉시콘 (KO + EN) | klue/roberta-base fine-tuned |
| Fusion | 가중합 (0.6 오디오 / 0.4 텍스트) | MLP on concatenated softmax vectors |

인터페이스(`classify_audio`, `classify_text`)는 고정 — 구현 교체 시 `EmotionService` 수정 불필요.
