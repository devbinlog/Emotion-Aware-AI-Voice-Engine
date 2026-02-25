# 프로젝트 규칙 — Emotion-Aware AI Voice Engine

Claude Code가 이 프로젝트에서 작업할 때 반드시 따르는 규칙.

---

## 문서 업데이트 규칙 (필수)

**새로운 기능 완성, 버그 수정, 성능 개선, 디자인 변경이 있을 때마다 반드시 아래를 갱신한다:**

1. **`DEVLOG.md`** (루트) — 새 항목 추가 (날짜, 변경 내용, 해결한 문제, 결과)
2. **`README.md`** (루트) — 최신 기능/상태 반영
3. **`reports/TROUBLESHOOTING.md`** — 새 오류와 해결 과정 추가 (해당하는 경우)

이 규칙은 선택이 아니다. 코드 변경과 문서 업데이트는 세트다.

---

## 백엔드 실행 방법

```bash
cd backend
KMP_DUPLICATE_LIB_OK=TRUE HF_HUB_OFFLINE=1 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- `KMP_DUPLICATE_LIB_OK=TRUE`: CTranslate2 + OpenMP 충돌 방지 (macOS 필수)
- `HF_HUB_OFFLINE=1`: HuggingFace 네트워크 요청 스킵

---

## 중요한 기술적 결정

### STT — 서브프로세스 격리
- faster-whisper (CTranslate2)는 uvicorn asyncio 이벤트 루프와 충돌 (macOS SIGABRT)
- `backend/stt_worker_process.py`를 별도 프로세스로 실행, stdin/stdout JSON 파이프 통신
- **절대로** asyncio 컨텍스트에서 직접 WhisperModel 초기화하지 말 것

### WebM 오디오 디코딩
- MediaRecorder Blob을 청크별로 `decodeAudioData` 하지 말 것 (WebM은 연속 스트림)
- 모든 Blob을 누적한 뒤 하나의 완전한 파일로 합쳐 디코딩할 것
- `end_stream`은 오디오 전송 완료 후에만 전송할 것

### 대화 히스토리
- 클라이언트 `historyRef`가 정보 출처
- WebSocket 재연결 시 `config` 메시지의 `history` 필드로 서버에 복원
- `reset()`은 히스토리도 초기화, `continueConversation()`은 히스토리 유지

---

## 파일 구조 요약

```
/
├── CLAUDE.md                  ← 이 파일 (프로젝트 규칙)
├── DEVLOG.md                  ← 개발 로그 (새 결과마다 업데이트)
├── README.md                  ← 프로젝트 개요
├── backend/
│   ├── stt_worker_process.py  ← STT 격리 서브프로세스 (절대 이동 금지)
│   └── app/
│       ├── services/llm_service.py  ← Ollama→Claude→템플릿 폴백
│       └── models/emotion_classifier.py  ← 규칙 기반 감정 분류기
├── frontend/
│   └── src/hooks/useVoicePipeline.ts  ← 핵심 WebSocket 훅
└── reports/
    └── TROUBLESHOOTING.md     ← 오류 해결 기록
```
