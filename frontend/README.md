# Frontend — Next.js

Emotion-Aware AI Voice Engine의 클라이언트.
Next.js 14 (App Router) + TypeScript + Tailwind CSS + Framer Motion

---

## 실행

```bash
cd frontend
npm install
npm run dev       # http://localhost:3000
```

백엔드(`uvicorn app.main:app --port 8000`)를 먼저 실행해야 합니다.
`next.config.mjs`의 `rewrites`가 `/api/*`, `/ws/*`를 8000포트로 프록시합니다.

---

## 구조

```
src/
├── app/
│   ├── layout.tsx          루트 레이아웃 (폰트, 메타데이터)
│   ├── page.tsx            메인 페이지 (대화 버블 + 녹음 + 분석)
│   └── globals.css         Tailwind + 라이트 모드 CSS 변수
├── components/
│   ├── VoiceButton.tsx     마이크 버튼 (Idle/Recording/Processing 상태)
│   ├── WaveformVisualizer.tsx  실시간 오디오 파형 (Canvas + Web Audio API)
│   ├── PipelineStatus.tsx  VAD→STT→감정→TTS 단계 인디케이터
│   ├── EmotionCard.tsx     감정 배지, 강도, 확률 바, 특징 값
│   ├── AudioPlayer.tsx     커스텀 오디오 플레이어 (감정 컬러, onEnded 콜백)
│   └── MetricsPanel.tsx    레이턴시 칩 (VAD/STT/감정/TTS/합계)
├── hooks/
│   └── useVoicePipeline.ts WebSocket 멀티턴 녹음 + REST 파일 업로드 통합 훅
└── types/
    └── pipeline.ts         공유 타입 + EMOTION_CONFIG + PIPELINE_STAGES
```

---

## UX 흐름

### WebSocket 모드 (마이크 녹음)

1. 마이크 버튼 클릭 → `getUserMedia` + WebSocket 연결
2. `config` 메시지로 voice, language, 대화 히스토리 전송
3. MediaRecorder 500ms 간격으로 Blob 누적 (디코딩 보류)
4. 정지 버튼 → 모든 Blob을 하나의 완전한 WebM으로 합쳐 `decodeAudioData`
5. Float32 PCM → base64 → `audio_chunk` 전송 → `end_stream` 전송
6. `vad_event` 수신 → VAD 실시간 바 업데이트
7. `final_transcript` 수신 → 대화 버블 갱신
8. `emotion` 수신 → 감정 카드 갱신
9. `ai_response` 수신 → AI 버블 갱신
10. `audio_chunk (is_last: true)` 수신 → Blob URL 생성 → 자동 재생
11. `metrics` 수신 → 레이턴시 패널 갱신
12. 오디오 재생 완료 → 현재 턴 저장 → `continueConversation()` → 다음 발화 대기

### REST 모드 (파일 업로드)

1. "파일 업로드" 클릭 → 오디오 파일 선택
2. `/api/transcribe` → `/api/analyze-emotion` → `/api/synthesize` 순차 호출
3. 각 단계 완료마다 해당 카드 갱신

---

## 멀티턴 대화 구현

```typescript
// useVoicePipeline.ts 핵심 구조

historyRef: { role: string; content: string }[]  // WebSocket 재연결에 걸쳐 유지

// 새 녹음 시작마다 히스토리를 서버에 전송
ws.send(JSON.stringify({ type: 'config', voice, language, history: historyRef.current }));

// 오디오 재생 완료 후 히스토리 업데이트
historyRef.current = [
  ...historyRef.current.slice(-18),
  { role: 'user',      content: pendingTr.current },
  { role: 'assistant', content: pendingAi.current },
];

// 소프트 리셋: 히스토리 보존, UI만 초기화
continueConversation();
```

---

## 디자인 시스템

| 토큰 | 값 |
|------|-----|
| 배경 | `#f2f2f7` (iOS/macOS 라이트) |
| 카드 | `#ffffff` |
| 텍스트 | `#09090b` |
| Muted | `#a1a1aa` |
| 사용자 버블 | `#18181b` (다크) |
| AI 버블 | `#ffffff` + 감정 컬러 왼쪽 3px 테두리 |
| 타이포 | Inter (Latin) / Noto Sans KR (Korean) |
| 감정 컬러 | 감정별 accent — `EMOTION_CONFIG` in `types/pipeline.ts` |

---

## 환경 변수

```bash
cp .env.local.example .env.local
```

백엔드가 `localhost:8000`이 아닌 경우에만 설정 필요:
- `NEXT_PUBLIC_API_URL`: REST base URL
- `NEXT_PUBLIC_WS_URL`: WebSocket URL (`ws://...`)
