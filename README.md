# Emotion Aware AI Voice Engine

감정 인식 기반 실시간 대화형 음성 AI 파이프라인

데모영상: 

자유 질문 -> 
대화 내용에 맞게 답변. 모르는 것이 있으면 인터넷 검색을 통해 생각하고 답변. 
아직 처리 속도가 매우 느림. 대화 문장 구조가 어색함. 감정 분석을 위해 더 좋은 마이크 필요.


[개발 로그](DEVLOG.md) · [기술 문서](docs/TECH.md) · [트러블슈팅](reports/TROUBLESHOOTING.md)

---

## 소개

사람이 말할 때 담기는 감정 — 목소리의 높낮이, 속도, 에너지 — 을 실시간으로 감지하고,
감지된 감정에 맞는 운율(prosody)로 AI가 응답하는 음성 대화 엔진.

선택한 TTS 캐릭터(Yuna, Samantha, Kyoko 등)에 따라 응답 언어가 자동으로 결정되고,
캐릭터 이름으로 자기소개하며 자연스러운 다국어 대화가 가능하다.

---

## 데모

<video src="assets/demo.mov" controls width="100%"></video>

---

## 파이프라인

```
마이크 / 파일
     │
     ▼  WebSocket 스트리밍
① VAD        발화 구간 감지 (silero-vad, 5–15ms)
② STT        한국어/영어 음성 → 텍스트 (faster-whisper base, 서브프로세스 격리)
③ 감정 분석  F0·RMS·ZCR·MFCC + 텍스트 키워드 → 6 클래스 감정 + 강도
④ 날씨 검색  날씨 키워드 감지 시 Open-Meteo API 실측 데이터 주입 (선택적)
⑤ LLM        감정 + 캐릭터 이름 + 언어 컨텍스트 포함 멀티턴 대화 응답
⑥ TTS        감정별 prosody 후처리 음성 합성 (macOS say, 다국어)
     │
     ▼
대화 버블 · 감정 분석 카드 · 음성 재생
```

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | FastAPI + WebSocket |
| VAD | silero-vad (fallback 내장) |
| STT | faster-whisper base, int8 (서브프로세스 격리) |
| 감정 분석 | numpy + scipy (F0/RMS/ZCR/MFCC 룰 엔진 + 텍스트 키워드) |
| LLM | Ollama qwen2.5:1.5b → Anthropic Claude API → 템플릿 폴백 |
| TTS | macOS say (ko/en/ja/zh 다국어) + scipy prosody 후처리 |
| 날씨 검색 | Open-Meteo API (무료, API 키 없음) |
| Frontend | Next.js 14 + Tailwind CSS + Framer Motion |
| 통신 | WebSocket JSON/base64 |

---

## 주요 기능

- 실시간 마이크 녹음 → 자동 파이프라인 처리 → 음성 응답
- 6가지 감정 감지: neutral · happy · sad · angry · excited · calm
- 감정별 TTS prosody 자동 조정 (피치 · 속도 · 에너지)
- 멀티턴 대화: 히스토리가 WebSocket 재연결에 걸쳐 유지됨
- 음성 재생 완료 후 자동으로 다음 발화 대기 전환
- 감정 확률 바, VAD 신뢰도, 레이턴시 패널 실시간 표시
- **음성 캐릭터별 응답 언어 자동 매칭**: Yuna→한국어, Samantha→영어, Kyoko→일본어
- **캐릭터 이름으로 자기소개**: "저는 유나예요", "I'm Samantha"
- **실시간 날씨 검색**: 날씨 질문 시 Open-Meteo 실측 데이터로 정확한 답변
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

### LLM 대화 활성화

```bash
# Ollama 로컬 LLM (무료, 권장)
brew install ollama
ollama serve &
ollama pull qwen2.5:1.5b   # ~1GB, 한국어 지원 경량 모델

# 더 나은 대화 품질 (선택)
ollama pull qwen2.5:7b     # ~4.7GB

# 또는 Anthropic Claude API
export ANTHROPIC_API_KEY=sk-ant-...
```

Ollama 없이 API 키도 없으면 감정 기반 템플릿 응답으로 자동 동작한다.

---

## 성능

macOS Apple M1, CPU-only, say TTS 기준

| 구간 | 시간 |
|------|------|
| VAD | 5–20ms |
| STT (2초 발화) | ~180ms |
| 감정 분석 | ~60ms |
| TTS | 200–500ms |
| **LLM (qwen2.5:1.5b, CPU)** | **7–12s** |

> LLM이 전체 지연의 대부분. GPU 또는 qwen2.5:7b 사용 시 품질·속도 모두 개선.

---

## 구조

```
/
├── CLAUDE.md                      프로젝트 규칙 (Claude Code용)
├── DEVLOG.md                      개발 로그
├── README.md                      이 파일
├── backend/
│   ├── stt_worker_process.py      STT 격리 서브프로세스 (이동 금지)
│   └── app/
│       ├── main.py                서버 시작 + 워밍업
│       ├── api/websocket.py       WS /ws/voice 파이프라인
│       ├── services/
│       │   ├── vad_service.py     발화 구간 감지
│       │   ├── stt_service.py     음성 → 텍스트
│       │   ├── emotion_service.py 감정 분석 (오디오 + 텍스트 융합)
│       │   ├── llm_service.py     LLM 대화 (Ollama → Claude → 템플릿)
│       │   ├── tts_service.py     음성 합성 + prosody 후처리
│       │   └── web_search.py      날씨 검색 (Open-Meteo)
│       └── models/
│           └── emotion_classifier.py  룰 기반 감정 분류기 (교체 가능)
├── frontend/src/
│   ├── app/page.tsx               메인 UI
│   ├── components/                UI 컴포넌트
│   └── hooks/useVoicePipeline.ts  핵심 WebSocket 훅
├── docs/TECH.md                   기술 상세 문서
└── reports/
    ├── TROUBLESHOOTING.md         오류 해결 기록
    └── model_choices.md           모델 선택 근거
```

---

## 문서

| 파일 | 내용 |
|------|------|
| [DEVLOG.md](DEVLOG.md) | 개발 과정, 기능 추가, 시행착오 기록 |
| [docs/TECH.md](docs/TECH.md) | 감정 분석 알고리즘, 특징 추출, 분류 규칙 상세 |
| [reports/TROUBLESHOOTING.md](reports/TROUBLESHOOTING.md) | 오류별 원인과 해결 과정 |
| [reports/model_choices.md](reports/model_choices.md) | 모델/엔진 선택 근거 |
