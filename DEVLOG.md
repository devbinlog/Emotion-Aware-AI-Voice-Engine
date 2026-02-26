# 개발 로그 — Emotion Aware AI Voice Engine

> 최신 항목이 맨 위, 초기 구현이 맨 아래에 위치한다.
> 상세 트러블슈팅은 `reports/TROUBLESHOOTING.md`, 기술 선택 근거는 `reports/model_choices.md`에 기록한다.

---

## 대화 말투 자연스러움 개선 + 헤더 정정

### 변경 내용

#### Backend
- `llm_service.py` — 언어별 독립 시스템 프롬프트 (`_SYSTEM_PROMPTS` 딕셔너리)
  - 기존: 영어 기본 프롬프트 + 언어별 지시어 병렬 구성 → 모델이 내부적으로 번역하며 번역체 한국어 생성
  - 변경: 각 언어의 프롬프트를 해당 언어로 완전히 작성 (`ko`/`en`/`ja`/`zh` 각각 독립)
  - 한국어 프롬프트에 금지 표현 명시: `'네,'` `'아,'` `'어떻게 도와드릴까요?'` `'무엇을 도와드릴까요?'` 시작 금지
  - 번역체 표현 금지, 자연스러운 존댓말 일관 사용 명시
  - `_get_system_prompt(language, name)` 헬퍼 함수로 단순화
  - 대화 히스토리 4개 → 2개 (직전 1턴만 유지, 속도 개선)

#### Frontend
- `page.tsx` — 헤더 이름 `Emotion-Aware AI Voice Engine` → `Emotion Aware AI Voice Engine` (대시 제거)

### 해결한 문제
- **번역체 말투**: 영어 지시로 인한 어색한 한국어 (`"오늘 많이 달라졌어요"`, `"필요한 help가 있다면"` 등) → 한국어 지시어로 직접 작성
- **형식적 시작**: `"네,"` `"아, 그래요?"` `"어떻게 도와드릴까요?"` 반복 → 금지 표현 명시
- **헤더 대시**: `Emotion-Aware` → `Emotion Aware`

### 현재 한계
- qwen2.5:1.5b (1.5B 파라미터) 모델 한계상 완벽한 자연스러움은 어렵다.
  더 나은 대화 품질을 원할 경우 `ollama pull qwen2.5:7b` 로 교체 가능 (약 4.7GB).

---

## 캐릭터 이름 정체성 + LLM 응답 속도 개선

### 변경 내용

#### Backend
- `llm_service.py`
  - `character_name` 파라미터 추가: 선택한 TTS 음성의 이름을 시스템 프롬프트에 주입
  - `num_predict: 100` → `60` (1-2문장 응답에 충분, 생성 시간 단축)
  - `num_ctx: 512` 추가 (컨텍스트 윈도우 축소 → prefill 빠름)
  - 대화 히스토리 6개 → 4개 메시지로 축소

- `websocket.py`
  - `_VOICE_NAME` 딕셔너리 추가: 음성 → 캐릭터 이름 매핑
  - `_voice_character_name()` 헬퍼 추가
  - `character_name`을 `get_llm_response`에 전달

#### Frontend
- `page.tsx` — 헤더 `Voice Engine` → `Emotion Aware AI Voice Engine`
- `AIBubble` — 레이블 `AI` 고정 → 선택된 캐릭터 이름 표시 (Yuna, Samantha 등)

### 해결한 문제
- **잘못된 자기소개**: 모델이 학습 데이터 기반으로 임의의 정체성 자기소개 → 이름을 시스템 프롬프트에 언어별로 주입
- **AI 버블 레이블**: `AI` 고정 → 선택된 음성 이름 표시
- **LLM 응답 지연**: `num_predict 100`, `num_ctx` 미설정 → 값 축소로 처리 시간 단축

### 결과
- "넌 누구야?" → "저는 유나예요" (Yuna), "I'm Samantha" (Samantha)
- 대화 버블 레이블이 실제 캐릭터 이름으로 표시됨

---

## 실시간 날씨 검색 + 다국어 응답 + 한자 필터 + 서버 워밍업

### 변경 내용

#### Backend
- `web_search.py` — 신규 생성
  - Open-Meteo API 연동: API 키 없이 무료 실시간 날씨 조회
  - 11개 한국 도시 좌표 테이블 (서울, 부산, 인천, 대구, 광주, 대전, 울산, 제주, 수원, 전주, 청주)
  - WMO 날씨 코드 → 한국어 날씨 설명 매핑
  - DuckDuckGo 일반 검색 비활성화 (감정 대화 컨텍스트 오염 방지)

- `llm_service.py`
  - `reply_language` 파라미터 추가 (공개 API → 내부 함수 전 체인)
  - `_clean_response()`: CJK 유니코드 범위(`\u4e00-\u9fff`) 정규식으로 한국어/영어 응답에서 한자 제거
  - 웹 검색 결과를 트랜스크립트에 주입 후 LLM 전달

- `websocket.py`
  - `_VOICE_LANG` 딕셔너리: TTS 음성 → 응답 언어 매핑
  - Yuna → `ko`, Kyoko → `ja`, Meijia/Tingting/Sinji → `zh`, 그 외 → `en`

- `main.py`
  - 서버 시작 시 STT 워커 사전 로드 (기존: 첫 요청 시 ~15초 대기)
  - Ollama qwen2.5:1.5b 워밍업 + `keep_alive: -1` 메모리 상주

### 해결한 문제
1. **날씨 거짓말**: LLM이 날씨를 임의로 생성 → Open-Meteo 실측 데이터 주입
2. **한자 혼입**: qwen2.5:1.5b가 한국어 응답에 漢字 누출 (忍受, 放松 등) → CJK 정규식 필터 제거
3. **캐릭터별 언어**: 영어 캐릭터 선택 시에도 한국어 응답 → 음성-언어 매핑으로 해결
4. **DDG 태그 오염**: `[검색 결과]` 태그가 AI 응답에 그대로 출력 → DDG 비활성화
5. **STT 콜드 스타트**: 첫 요청에 15초 지연 → 서버 시작 시 워커 사전 로드

### 결과
- "서울 지금 날씨 어때?" → Open-Meteo 실측 데이터로 정확한 답변
- Yuna(한국어), Samantha(영어), Kyoko(일본어) 각각 해당 언어로 응답
- 한자 누출 완전 제거
- STT 첫 요청 대기 해소 (서버 시작 후 워밍업 자동 완료)

---

## 음성 입력 복구 + 실제 대화 AI 연동 + UI 수정

### 변경 내용

#### Frontend
- `useVoicePipeline.ts` — 브라우저 WebAudio 디코딩 완전 제거
  - 기존: `AudioContext({sampleRate:16000}).decodeAudioData()` → rms≈0.0001 (사실상 무음)
  - 변경: 모든 WebM Blob 누적 후 base64 인코딩, `encoding: 'webm'` 필드와 함께 전송
  - `getUserMedia`에 `echoCancellation: false, noiseSuppression: false, autoGainControl: false` 추가
  - `micStream` 상태를 훅에서 외부로 노출
- `page.tsx` — 헤더 z-index `z-10` → `z-30` (사용자 버블이 헤더 위로 겹치는 현상 수정)
- `page.tsx` — `WaveformVisualizer`에 실제 `micStream` 전달

#### Backend
- `websocket.py` — `_ffmpeg_decode()` 함수 추가
  - `encoding: 'webm'` 청크를 받으면 ffmpeg로 서버에서 디코딩 (`f32le`, 16kHz, mono)
- `config.py` — `WHISPER_MODEL_SIZE` `"tiny"` → `"base"` (한국어 인식률 개선)
- `llm_service.py` — Ollama 실제 대화 연동
  - 모델: `llama3.2` → `qwen2.5:1.5b` (한국어 품질 최적화)
  - `keep_alive: -1`, `temperature: 0.7` 추가
- `main.py` — 서버 startup 시 Ollama 모델 워밍업

### 해결한 문제
1. **macOS WebAudio 버그**: `AudioContext({sampleRate:16000})`가 macOS에서 무음 PCM 생성 → ffmpeg 서버사이드 디코딩으로 우회
2. **WaveformVisualizer 항상 idle**: `stream={null}` 하드코딩 → 실제 micStream 연결
3. **LLM 언어 혼용**: llama3.2가 한국어에 영어/베트남어/한자 혼용 → qwen2.5:1.5b로 전환
4. **Ollama 첫 응답 60초+ 지연**: startup 워밍업 + keep_alive:-1으로 해결

### 결과
- 음성 입력 → ffmpeg 디코딩 → STT → 감정 분석 → qwen2.5:1.5b 대화 → TTS 전체 파이프라인 정상 작동
- 완전 무료 로컬 대화 AI (외부 API 키 불필요)

---

## 음성 입력 안정성 + 분석 결과 유지

### 변경 내용

- `useVoicePipeline.ts` — `recorder.onstop` 이벤트 기반으로 전환 (기존: setTimeout 350ms)
  - `onstop`은 마지막 `ondataavailable` 발생 보장 후 실행 → Blob 누락 없음
- `page.tsx` — `lastEmotion`, `lastMetrics` 상태 추가
  - 재생 완료 후 이전 분석을 유지하여 2번째 턴부터도 감정 카드/레이턴시 표시

### 해결한 문제
- 음성이 간헐적으로 안 들어가는 문제 → onstop 이벤트로 안정적 처리
- 2번째 턴부터 감정 카드, 레이턴시 패널이 사라지는 문제 → lastEmotion/lastMetrics 유지

---

## 멀티턴 대화 + 라이트 UI + STT 레이스 컨디션 수정

### 변경 내용

#### Frontend
- `useVoicePipeline.ts` 완전 재작성
  - STT 레이스 컨디션 수정: Blob을 누적 후 하나의 완전한 WebM으로 디코딩
  - `historyRef`: 대화 히스토리를 WebSocket 재연결에 걸쳐 유지
  - `continueConversation()`: 히스토리 보존 소프트 리셋 / `reset()`: 완전 초기화
- `page.tsx` 레이아웃 재구성: 대화(위) → 녹음(중간) → 분석(아래)
  - `turns` 배열로 완료된 대화 턴 저장, 버블 형태로 표시
  - `handlePlayEnd`: 재생 완료 시 자동으로 다음 발화 대기 전환
- 라이트 모드 전환: `--bg: #f2f2f7`, `--card: #ffffff`
- 대화 버블: 사용자(오른쪽 다크), AI(왼쪽 화이트 + 감정 색 왼쪽 테두리)
- 감정별 배경 Gradient (헤더 상단)

#### Backend
- `websocket.py`: `config` 메시지에서 클라이언트 대화 히스토리 복원
- `emotion_classifier.py`: 임계값 완화, F0=0 폴백, 규칙 R6/R7 추가, neutral 베이스라인 낮춤
- `llm_service.py` 생성: Ollama → Anthropic Claude → 템플릿 폴백 체인

### 해결한 문제
- STT 항상 빈 결과 → WebM 레이스 컨디션 수정
- 감정 항상 neutral → 임계값 완화 + F0 폴백
- LLM 고정 응답 → 실제 트랜스크립트 기반 멀티턴 대화

---

## 음성 파이프라인 기초 구현

### 아이디어

동기: 기존 챗봇은 텍스트만 처리하고 비언어적 신호(목소리 높낮이, 속도, 에너지)를 무시한다.
이 프로젝트는 음성의 감정을 인식하고 그 감정에 맞는 목소리 톤으로 응답하는 AI를 만드는 것이 목표다.

### 기술 스택 선택 근거

| 컴포넌트 | 선택 | 이유 |
|----------|------|------|
| Backend | FastAPI | 비동기 네이티브, WebSocket 지원 |
| VAD | silero-vad | 5–15ms 처리, graceful fallback |
| STT | faster-whisper (base, int8) | CTranslate2 최적화, 한국어 지원, CPU 실행 |
| 감정 오디오 | numpy + scipy | librosa 의존성 없음 (llvmlite 빌드 실패), GPU 불필요 |
| 감정 텍스트 | 키워드 렉시콘 (KO+EN) | MVP 수준, KoBERT로 업그레이드 경로 명확 |
| LLM | Ollama → Claude API → 템플릿 | 로컬 우선, API 키 없어도 동작 |
| TTS | macOS `say` (다국어) + scipy prosody | 한국어 내장, 설치 불필요 |
| Frontend | Next.js 14 + Tailwind + Framer Motion | App Router, 애니메이션 내장 |

### 초기 구현

- FastAPI WebSocket 엔드포인트 `/ws/voice`
- VADService → STTService → EmotionService → TTSService 순차 파이프라인
- 감정 분석: F0 자기상관 + RMS + ZCR + MFCC × 13 + 발화속도
- prosody 후처리: 감정별 pitch/rate/energy 조정

### 초기 오류 요약

| # | 오류 | 해결 |
|---|------|------|
| 1 | librosa/numba 빌드 실패 | numpy/scipy로 재구현 |
| 2 | numpy 2.x + torch 비호환 | `pip install "numpy<2"` |
| 3 | FastAPI 시작 시 torch crash | lazy import |
| 4 | SIGABRT (macOS) | STT 서브프로세스 격리 |
| 5 | afconvert 오버헤드 | soundfile AIFF 직접 읽기 |
| 6 | WAV 청킹 버그 | 전체를 단일 blob으로 전송 |
| 7 | LLM 고정 응답 | Ollama 설치 또는 API 키 설정 |
| 8 | STT 항상 빈 값 (Race Condition) | Blob 누적 후 단일 WebM 디코딩 |
| 9 | 감정 항상 neutral | 임계값 완화 + F0=0 폴백 |

---

## 현재 결과물 요약

### 동작하는 기능
- 실시간 마이크 → WebSocket → STT → 감정 분석 → LLM 응답 → TTS → 브라우저 재생
- 멀티턴 대화 히스토리 (WebSocket 재연결에도 유지)
- 음성 재생 완료 후 자동으로 다음 발화 대기 전환
- 6가지 감정 감지: neutral · happy · sad · angry · excited · calm
- 감정별 TTS prosody 자동 조정 (pitch · rate · energy)
- 음성 캐릭터별 자동 언어 매칭 (Yuna→한국어, Samantha→영어, Kyoko→일본어 등)
- 캐릭터 이름으로 자기소개 ("저는 유나예요", "I'm Samantha")
- 실시간 날씨 검색 (Open-Meteo, 11개 한국 도시, API 키 없음)
- 한자 누출 방지 (CJK 정규식 후처리)
- 서버 시작 시 STT + LLM 자동 워밍업 (첫 요청 지연 없음)
- VAD 신뢰도, 레이턴시(VAD/STT/감정/TTS) 실시간 표시
- 음성 종류 선택, 오디오 파일 업로드 지원

### UI
- 라이트 모드 (`#f2f2f7` 배경)
- 대화 버블 (사용자: 오른쪽 다크, AI: 왼쪽 화이트 + 감정 색 왼쪽 테두리)
- 감정별 subtle 배경 그라디언트 (헤더 상단)
- 레이아웃: 대화(위) → 녹음(중간) → 분석(아래)

### 성능 (macOS M1 CPU, say TTS 기준)

| 입력 | STT | 감정 | TTS | LLM | 합계 |
|------|:---:|:----:|:---:|:---:|:----:|
| 2초 발화 | 180ms | 60ms | 400ms | 7-10s | ~8-11s |
| 5초 발화 | 300ms | 80ms | 500ms | 7-10s | ~8-11s |

> LLM(qwen2.5:1.5b, CPU)이 전체 지연의 대부분을 차지한다.
> GPU 또는 더 큰 모델(qwen2.5:7b) 사용 시 품질과 속도 모두 개선 가능.

---

## 향후 계획

| 영역 | 내용 |
|------|------|
| LLM 품질 | qwen2.5:7b 또는 GPU 환경으로 전환 |
| 감정 ML | ECAPA-TDNN SER (오디오) + klue/roberta (텍스트) |
| STT 품질 | whisper `small` 전환 |
| 한국어 TTS | XTTS v2 (GPU) 또는 한국어 VITS |
| 스트리밍 STT | 실시간 부분 트랜스크립트 |
