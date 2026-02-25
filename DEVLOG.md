# 개발 로그 — Emotion-Aware AI Voice Engine

> 이 파일은 새로운 기능/결과/오류 해결이 있을 때마다 업데이트된다.
> 최신 항목이 맨 위에 위치한다.

---

## 업데이트 규칙

- 새 기능 완성, 버그 수정, 디자인 변경, 성능 개선 이 있을 때마다 본 파일을 갱신한다.
- 각 항목은 날짜, 변경 내용, 해결한 문제, 결과 형식으로 작성한다.
- 상세 트러블슈팅은 `reports/TROUBLESHOOTING.md` 에, 기술 선택 근거는 `reports/model_choices.md` 에 작성한다.

---
## 음성 파이프라인 기초 구현 + 초기 오류 해결

### 아이디어의 시작

동기: 사람이 대화할 때 단순히 "무엇을 말했는가" 뿐 아니라 "어떤 감정으로 말했는가"가 중요하다. 기존 챗봇은 텍스트만 처리하고 비언어적 신호(목소리 떨림, 높낮이, 속도)를 무시한다. 이 프로젝트는 음성의 감정을 인식하고 그 감정에 맞는 목소리 톤으로 응답하는 AI를 만드는 것이 목표다.

핵심 아이디어:
1. 마이크 입력에서 실시간으로 감정 감지
2. 감지된 감정을 LLM 프롬프트와 TTS 음성 파라미터 양쪽에 반영
3. 브라우저에서 즉시 인터랙션 가능한 UI

### 기술 스택 선택 근거

| 컴포넌트 | 선택 | 이유 |
|----------|------|------|
| Backend | FastAPI | 비동기 네이티브, WebSocket 지원, 자동 OpenAPI |
| VAD | silero-vad | 5–15ms 처리, 추가 패키지 없음, graceful fallback |
| STT | faster-whisper (tiny, int8) | OpenAI Whisper의 CTranslate2 최적화판, 한국어 지원, CPU 실행 |
| 감정 오디오 | numpy + scipy | librosa 의존성 없음 (llvmlite 빌드 실패 이슈), GPU 불필요, 완전 해석 가능 |
| 감정 텍스트 | 키워드 렉시콘 (KO+EN) | 초기 MVP, KoBERT/klue-bert로 업그레이드 경로 명확 |
| LLM | Ollama → Claude API → 템플릿 | 로컬 우선, API 키 없어도 동작, 멀티턴 지원 |
| TTS | macOS `say` (Yuna, ko_KR) | 한국어 내장, 설치 불필요, 200–500ms |
| TTS 후처리 | scipy resample_poly | librosa 없이 pietch/time-stretch 구현 |
| Frontend | Next.js 14 + TailwindCSS + Framer Motion | React 기반, App Router, 애니메이션 내장 |
| 스트리밍 | WebSocket + JSON/base64 | 저지연 양방향, 브라우저 네이티브 |

### 초기 구현

- FastAPI WebSocket 엔드포인트 `/ws/voice`
- `VADService` → `STTService` → `EmotionService` → `TTSService` 순차 파이프라인
- 브라우저 MediaRecorder → float32 PCM → base64 → WebSocket 전송
- 감정 분석: F0 자기상관 + RMS + ZCR + MFCC × 13 + 발화속도
- prosody 후처리: 감정별 pietch/rate/energy 조정
- 

## 음성 입력 안정성 + 분석 결과 유지

### 변경 내용

Frontend
- `useVoicePipeline.ts` — `stopRecording`: `setTimeout(350ms)` → `recorder.onstop` 이벤트 기반으로 전환
  - `onstop`은 마지막 `ondataavailable` 발생 보장 후에 실행 → Blob 누락 없음
- `page.tsx` — 분석(감정/메트릭스) 유지 로직 추가
  - `lastEmotion`, `lastMetrics` 상태 추가
  - `handlePlayEnd`에서 현재 감정/메트릭스를 저장
  - `displayEmotion = state.emotion ?? (turns > 0 ? lastEmotion : null)` 패턴
  - `PipelineMetrics` 타입 import 추가

### 해결한 문제
- 음성이 잘 안 들어가는 문제 → onstop 이벤트로 안정적 처리
- 2번째 턴부터 분석(감정 카드, 레이턴시)이 사라지는 문제 → lastEmotion/lastMetrics로 유지

### 결과
- 첫 응답 전: 분석 없음 (정상)
- 첫 응답 후 2번째 이상: 이전 분석이 유지되며, 새 응답이 오면 업데이트됨
- 초기화 버튼 클릭 시에만 분석 사라짐

---

## 멀티턴 대화 + 라이트 UI + STT 레이스 컨디션 수정

### 변경 내용

Frontend
- `useVoicePipeline.ts` 완전 재작성
  - STT 레이스 컨디션 수정: MediaRecorder Blob을 누적 후 하나의 완전한 WebM 파일로 디코딩 (이전: 500ms 청크를 각각 decodeAudioData → 실패)
  - `historyRef`: 대화 히스토리를 WebSocket 재연결에 걸쳐 유지
  - `continueConversation()`: 대화 히스토리를 보존하는 소프트 리셋
  - `reset()`: 히스토리 포함 완전 초기화
- `page.tsx` 레이아웃 재구성
  - 대화 (위) → 녹음 (중간) → 분석 (아래) 순서
  - `turns` 배열: 완료된 대화 턴을 저장, 대화 버블 형태로 표시
  - `handlePlayEnd`: 오디오 재생 완료 시 자동으로 다음 녹음 대기 상태로 전환
  - 음성 선택기, 초기화 버튼 헤더에 배치
- 라이트 모드 전환: `--bg: #f2f2f7`, `--card: #ffffff`
- 대화 버블: 사용자(오른쪽, 다크), AI(왼쪽, 화이트+감정 왼쪽 테두리)
- 감정별 배경 Gradient (헤더 상단 subtle tint)
- 컴포넌트 라이트 모드 업데이트: EmotionCard, VoiceButton, MetricsPanel, PipelineStatus

Backend
- `websocket.py`: `config` 메시지에서 클라이언트 대화 히스토리 복원
- `emotion_classifier.py`: 실제 마이크 입력에 맞게 임계값 완화, F0=0 폴백, 새 규칙 R6/R7 추가, neutral 베이스라인 낮춤
- `llm_service.py` 생성: Ollama → Anthropic Claude Haiku → 템플릿 폴백 체인

### 해결한 문제
- STT 항상 빈 결과 → WebM 레이스 컨디션 수정으로 해결
- 감정 항상 neutral → 임계값 완화 + F0 폴백으로 해결
- LLM 고정 응답 → 실제 트랜스크립트 기반 멀티턴 대화로 전환

### 결과
- 음성 녹음 → STT → 감정 분석 → LLM 응답 → TTS 전체 파이프라인 정상 작동
- 대화 히스토리가 WebSocket 재연결에 걸쳐 유지되어 멀티턴 대화 가능
- 오디오 재생 완료 후 자동으로 다음 발화 대기 상태로 전환

### 주요 오류와 해결 과정

#### 1. librosa 설치 실패
오류: `numba requires llvmlite → llvmlite build failed`
해결: librosa 제거, numpy/scipy로 모든 음성 처리 직접 구현
상세: [reports/TROUBLESHOOTING.md #1](reports/TROUBLESHOOTING.md)

#### 2. numpy 2.x + torch 비호환
오류: `A module compiled with NumPy 1.x cannot be run in NumPy 2.x`
해결: `pip install "numpy<2"` → numpy 1.26.4
상세: [reports/TROUBLESHOOTING.md #2](reports/TROUBLESHOOTING.md)

#### 3. FastAPI 시작 시 torch import crash
오류: config.py 최상위에서 `torch.cuda.is_available()` 호출
해결: lazy import + try/except 패턴
상세: [reports/TROUBLESHOOTING.md #3](reports/TROUBLESHOOTING.md)

#### 4. SIGABRT — 핵심 충돌 (macOS)
오류: 음성 요청 시마다 Python "예기치 않은 종료" 팝업
원인: CTranslate2 (faster-whisper) + uvicorn asyncio 이벤트 루프 스레드 충돌
해결: STT를 완전히 분리된 서브프로세스(`stt_worker_process.py`)로 격리, stdin/stdout JSON 파이프 통신
결과: SIGABRT 완전 해소
상세: [reports/TROUBLESHOOTING.md #4](reports/TROUBLESHOOTING.md)

#### 5. afconvert 지연
오류: TTS 음성이 0.1초짜리 노이즈처럼만 출력됨
원인: macOS `say` → AIFF → `afconvert` → WAV 변환 과정에서 오버헤드
해결: soundfile이 AIFF 직접 읽기 지원 → `afconvert` 단계 제거
상세: [reports/TROUBLESHOOTING.md #5](reports/TROUBLESHOOTING.md)

#### 6. WAV 청킹 버그
오류: 오디오가 재생되지 않거나 일부만 재생됨
원인: WAV 파일을 여러 청크로 나눠 전송하면 각 청크에 WAV 헤더가 붙어 클라이언트가 첫 헤더만 파싱
해결: 전체 오디오를 하나의 WAV blob으로 전송 (`is_last: true`)

#### 7. LLM 고정 응답
원인: Ollama 미설치, `ANTHROPIC_API_KEY` 미설정 → 템플릿 폴백 사용
해결: Ollama 또는 Anthropic API 키 설정 안내 문서화
상세: [reports/TROUBLESHOOTING.md #7](reports/TROUBLESHOOTING.md)

#### 8. STT 트랜스크립트 항상 빈 값 (레이스 컨디션)
오류: 녹음해도 `transcript: ''` 항상 빈 값
원인: MediaRecorder WebM 청크 별 `decodeAudioData` 비동기 작업이 `end_stream` 전송 후 도착
해결: 모든 Blob 누적 후 완전한 WebM 파일로 합쳐 디코딩, `end_stream`은 오디오 전송 후 발송
상세: [reports/TROUBLESHOOTING.md #8](reports/TROUBLESHOOTING.md)

#### 9. 감정 항상 neutral
원인: F0 자기상관 실패(0 반환) + 임계값이 실제 마이크 입력보다 엄격
해결: F0=0 폴백 처리, 임계값 완화, 규칙 추가, neutral 베이스라인 낮춤
상세: [reports/TROUBLESHOOTING.md #9](reports/TROUBLESHOOTING.md)

---

## 현재 결과물 요약

### 동작하는 기능
- 실시간 마이크 녹음 → WebSocket 스트리밍 → STT → 감정 분석 → LLM 응답 → TTS → 브라우저 재생
- 멀티턴 대화: 대화 히스토리가 WebSocket 재연결에 걸쳐 보존됨
- 오디오 재생 완료 후 자동으로 다음 발화 준비 상태로 전환
- 감정별 색상/이모지/확률 바 실시간 표시
- VAD 신뢰도 실시간 표시
- 레이턴시 측정 (VAD/STT/감정/TTS 별도 표시)
- 음성 선택 (macOS 설치 음성 목록 자동 조회)
- 오디오 파일 업로드 (REST 모드)
- 대화 초기화 버튼

### UI
- 라이트 모드 (`#f2f2f7` 배경)
- 대화 버블 (사용자: 오른쪽 다크, AI: 왼쪽 화이트 + 감정 색 왼쪽 테두리)
- 감정별 subtle 배경 그라디언트 (헤더 상단)
- 레이아웃: 대화(위) → 녹음(중간) → 분석(아래)

### 성능 (macOS M1 CPU, say TTS)
- 2초 발화: VAD 10ms + STT 180ms + 감정 60ms + TTS 400ms = ~650ms
- 5초 발화: VAD 20ms + STT 300ms + 감정 80ms + TTS 500ms = ~900ms

---

## 향후 계획

| 영역 | 내용 |
|------|------|
| 감정 ML | ECAPA-TDNN SER (오디오) + klue/roberta (텍스트) |
| STT 품질 | whisper `small` 전환 |
| 한국어 TTS | XTTS v2 (GPU) 또는 한국어 VITS |
| 스트리밍 STT | 실시간 부분 트랜스크립트 |
| 화자 분리 | pyannote-audio |
