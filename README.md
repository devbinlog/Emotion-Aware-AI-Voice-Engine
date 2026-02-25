# Emotion-Aware AI Voice Engine

감정 인식 기반 실시간 대화형 음성 AI 파이프라인

[개발 로그](DEVLOG.md) · [기술 문서](docs/TECH.md) · [트러블슈팅](reports/TROUBLESHOOTING.md)

---

## 소개

사람이 말할 때 담기는 감정 — 목소리의 높낮이, 속도, 에너지 — 을 실시간으로 감지하고,
감지된 감정에 맞는 운율(prosody)로 AI가 응답하는 음성 대화 엔진.

일반 소비자 하드웨어(CPU)에서 왕복 약 650ms 이내에 전체 파이프라인이 동작한다.

---

## 파이프라인

```
마이크 / 파일
     │
     ▼  WebSocket 스트리밍
① VAD        발화 구간 감지 (silero-vad, 5–15ms)
② STT        한국어/영어 음성 → 텍스트 (faster-whisper tiny)
③ 감정 분석  F0·RMS·ZCR·MFCC + 텍스트 키워드 → 6 클래스 감정 + 강도
④ LLM        감정 컨텍스트 포함 멀티턴 대화 응답
⑤ TTS        감정별 prosody 후처리 음성 합성 (macOS say)
     │
     ▼
대화 버블 · 감정 분석 카드 · 음성 재생
```

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | FastAPI + WebSocket |
| VAD | silero-vad |
| STT | faster-whisper tiny (서브프로세스 격리) |
| 감정 분석 | numpy + scipy (F0/RMS/ZCR/MFCC 룰 엔진 + 텍스트 키워드) |
| LLM | Ollama → Anthropic Claude API → 템플릿 폴백 |
| TTS | macOS say (Yuna ko_KR) + scipy prosody 후처리 |
| Frontend | Next.js 14 + Tailwind CSS + Framer Motion |
| 통신 | WebSocket JSON/base64 |

---

## 주요 기능

- 실시간 마이크 녹음 → 자동 파이프라인 처리 → 음성 응답
- 6가지 감정 감지: neutral · happy · sad · angry · excited · calm
- 감정별 TTS prosody 자동 조정 (피치 · 속도 · 에너지)
- 멀티턴 대화: 히스토리가 WebSocket 재연결에 걸쳐 유지됨
- 음성 재생 완료 후 자동으로 다음 발화 대기 전환
- 감정 확률 바, VAD 실시간 표시, 레이턴시 패널
- 음성 종류 선택, 오디오 파일 업로드 지원

---

## 실행

```bash
# 백엔드
cd backend
pip install -r requirements.txt
KMP_DUPLICATE_LIB_OK=TRUE HF_HUB_OFFLINE=1 uvicorn app.main:app --host 0.0.0.0 --port 8000

# 프론트엔드
cd frontend
npm install
npm run dev
```

> macOS에서 `KMP_DUPLICATE_LIB_OK=TRUE` 는 필수. 없으면 CTranslate2 + OpenMP 충돌로 서버가 종료된다.

### LLM 대화 활성화 (선택)

```bash
# Ollama 로컬 LLM
brew install ollama && ollama serve & ollama pull llama3.2

# 또는 Anthropic Claude API
export ANTHROPIC_API_KEY=sk-ant-...
```

두 옵션 모두 없으면 감정 기반 템플릿 응답으로 자동 동작한다.

---

## 성능

macOS Apple M1, CPU-only, say TTS 기준

| 입력 | VAD | STT | 감정 | TTS | 합계 |
|------|:---:|:---:|:----:|:---:|:----:|
| 2초 발화 | 10ms | 180ms | 60ms | 400ms | ~650ms |
| 5초 발화 | 20ms | 300ms | 80ms | 500ms | ~900ms |

---

## 구조

```
/
├── backend/
│   ├── stt_worker_process.py     STT 격리 서브프로세스
│   └── app/
│       ├── api/websocket.py      WS /ws/voice 파이프라인
│       ├── services/             VAD · STT · 감정 · LLM · TTS
│       └── models/               감정 분류기 (교체 가능)
├── frontend/src/
│   ├── app/page.tsx              메인 UI
│   ├── components/               UI 컴포넌트
│   └── hooks/useVoicePipeline.ts WebSocket 훅
├── docs/TECH.md                  기술 상세 문서
└── reports/                      벤치마크 · 트러블슈팅
```

---

## 문서

| 파일 | 내용 |
|------|------|
| [docs/TECH.md](docs/TECH.md) | 감정 분석 알고리즘, 특징 추출, 분류 규칙 상세 |
| [DEVLOG.md](DEVLOG.md) | 개발 과정, 아이디어, 시행착오 기록 |
| [reports/TROUBLESHOOTING.md](reports/TROUBLESHOOTING.md) | 오류별 원인과 해결 과정 |
| [reports/model_choices.md](reports/model_choices.md) | 모델/엔진 선택 근거 |
