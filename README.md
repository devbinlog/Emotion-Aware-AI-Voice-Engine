# Emotion-Aware AI Voice Engine

AI Sound & Voice Engineer
> 감정 인식 기반의 실시간 대화형 음성 AI 파이프라인

---

## 프로젝트 개요

사람마다 목소리에 감정이 담겨 있다. 이 프로젝트는 사용자의 음성에서 감정 상태를 실시간으로 감지하고, 감지된 감정에 맞는 운율(prosody)로 응답 음성을 합성하는 엔드-투-엔드 파이프라인을 구현한다.

목표: 일반 소비자 하드웨어(CPU)에서 왕복 1.5초 이내의 지연으로 감정 공감 대화를 구현한다.

> 개발 과정, 아이디어, 오류 해결 기록: [DEVLOG.md](DEVLOG.md)

---

## 최신 업데이트

### 멀티턴 연속 대화
- 오디오 재생 완료 후 자동으로 다음 발화 대기 상태로 전환
- 대화 히스토리가 WebSocket 재연결에 걸쳐 클라이언트-서버 양방향으로 동기화
- LLM이 이전 대화 맥락을 기억하여 자연스러운 멀티턴 대화 구현

### STT 레이스 컨디션 수정
- MediaRecorder WebM 청크를 누적 후 하나의 완전한 파일로 합쳐 디코딩 (기존: 청크별 개별 디코딩 시도 → 실패)
- `end_stream` 신호를 오디오 전송 완료 후 발송하여 서버 측 빈 버퍼 문제 해소

### UI 대화형 레이아웃
- 대화 버블 (사용자: 오른쪽, AI: 왼쪽)
- 레이아웃 순서: 대화 히스토리(위) → 녹음 컨트롤(중간) → 감정 분석(아래)
- 라이트 모드 (`#f2f2f7` 배경, 흰색 카드)

---

## 파이프라인

```
브라우저 마이크 / 오디오 파일
         │
         ▼ (WebSocket 청크 / HTTP 업로드)
┌─────────────────────────────────────────────────────────┐
│  FastAPI 백엔드                                          │
│                                                          │
│  ① VAD (silero-vad)                                     │
│     └─ 발화 구간 감지, 노이즈 게이팅                     │
│         │                                                │
│  ② STT (faster-whisper tiny, int8 · 서브프로세스 격리)  │
│     └─ 한국어/영어 음성 → 텍스트 + 언어 자동 감지       │
│         │                                                │
│  ③ 감정 분석 (Audio Branch + Text Branch + Fusion)      │
│     ├─ 오디오: F0, RMS, ZCR, MFCC × 13, 발화속도       │
│     ├─ 텍스트: 감정 키워드 렉시콘 (KO + EN)              │
│     └─ Fusion: 0.6 × audio_prob + 0.4 × text_prob       │
│         │                                                │
│  ④ LLM 응답 생성                                        │
│     ├─ Ollama (로컬) → Anthropic Claude API → 템플릿    │
│     └─ 감정 컨텍스트 포함 멀티턴 대화 히스토리          │
│         │                                                │
│  ⑤ TTS (macOS say Yuna / Coqui VITS / Piper)           │
│     └─ 음성 합성 → scipy prosody 후처리                  │
│         (피치 시프트 · 시간 신축 · 에너지 스케일)         │
│         │                                                │
│  ⑥ 오디오 스트리밍 (WebSocket WAV / HTTP 응답)           │
└─────────────────────────────────────────────────────────┘
         │
         ▼
브라우저: 대화 버블 · 감정 배너 · 음성 재생 · 레이턴시 표시
```

---

## 감정 분석 상세 — 기준점과 알고리즘

감정 분류는 음성 신호 처리(Audio Branch)와 텍스트 감정 분석(Text Branch) 두 갈래를 병렬로 실행한 뒤 융합(Fusion)한다.

### 감정 클래스

| 라벨 | 한국어 | 특징 |
|------|--------|------|
| `neutral` | 중립 | 기본 베이스라인 |
| `happy` | 행복 | 높은 피치, 중간 에너지 |
| `sad` | 슬픔 | 낮은 피치, 낮은 에너지, 느린 속도 |
| `angry` | 분노 | 높은 에너지, 높은 ZCR, 불규칙한 피치 |
| `excited` | 흥분 | 가장 높은 피치+에너지+속도 조합 |
| `calm` | 차분 | 낮은 에너지, 낮은 피치 변화, 규칙적 속도 |

---

### Audio Branch — 음성 특징 추출

오디오는 16kHz 모노 float32 PCM으로 정규화한 뒤 아래 5가지 특징군을 추출한다.

#### 1. F0 (기본 주파수, Fundamental Frequency)

정의: 사람이 목소리를 낼 때 성대가 진동하는 주파수 (단위: Hz).

추출 방법: 자기상관(Autocorrelation) 기반 F0 추정
```
각 프레임(2048 샘플, hop=512):
  1. 프레임 평균 제거 (DC offset 제거)
  2. 정규화된 자기상관 계산: R[τ] = Σ x[t]·x[t+τ]
  3. 탐색 범위: τ ∈ [sr/f_max, sr/f_min] → 65Hz–2093Hz 대역
  4. 자기상관 피크 위치 τ_peak → F0 = sr / τ_peak
  5. R[τ_peak] / R[0] > 0.25 → 유성음(voiced) 판정
```

기준값 (16kHz 일반 대화 음성):

| 범위 | 해석 |
|------|------|
| F0 < 130Hz | 낮은 목소리 → sad 경향 |
| 130–175Hz | 중립적 |
| 175–210Hz | 다소 높음 → happy 경향 |
| F0 > 210Hz | 매우 높음 → excited 경향 |
| F0_std < 22Hz | 단조로움 → calm / sad |
| F0_std > 45Hz | 변동 큼 → angry / excited |

> 기준 출처: 한국어 자연 발화 연구에서 성인 남/녀 기본 F0는 평균 120–220Hz 범위이며, 흥분/긍정 감정에서 유의미하게 상승하는 것이 관찰됨 (참조: Scherer 2003, Speech and emotion). 본 구현은 해당 범위를 실험적으로 조정함.

#### 2. RMS (Root Mean Square Energy)

정의: 오디오 신호의 평균 진폭 에너지. => 목소리의 크기(음량).

```
각 프레임: RMS = sqrt(mean(frame²))
전체 통계: rms_mean = mean(RMS_all_frames)
```

기준값:

| 범위 | 해석 |
|------|------|
| rms < 0.04 | 아주 작은 목소리 → sad |
| 0.04–0.055 | 조용한 목소리 → calm / neutral |
| 0.055–0.09 | 보통 크기 → neutral / happy |
| rms > 0.09 | 큰 목소리 → angry / excited |

> 16kHz float32 정규화 기준. 실제 마이크 입력은 0–1 범위로 정규화된 값.

#### 3. ZCR (Zero Crossing Rate)

정의: 신호가 0을 가로지르는 횟수의 비율. 마찰음(ㅅ, ㅈ, ㅊ)이나 흥분·분노 상태에서 증가.

```
각 프레임: ZCR = mean(|sign(x[t]) - sign(x[t-1])| / 2)
```

기준값:

| 범위 | 해석 |
|------|------|
| zcr < 0.10 | 낮음 → 유성음 주도, calm / sad |
| 0.10–0.15 | 보통 |
| zcr > 0.15 | 높음 → 마찰음 많음, angry / excited |

#### 4. MFCC (Mel-Frequency Cepstral Coefficients)

정의: 인간의 청각 특성을 모방한 스펙트럼 특징. 13개 계수로 음색과 조음 방식을 압축 표현.

추출 과정:
```
1. 프레임 × Hanning 윈도우
2. FFT → 파워 스펙트럼 |X(f)|²
3. Mel 필터뱅크(40개) 적용: Mel 주파수 = 2595·log10(1 + Hz/700)
4. 로그 변환: log(mel_energy)
5. Type-III DCT → MFCC 1~13번 계수
```

> MFCC는 현재 감정 분류기에서 보조 특징으로 저장되며, 향후 ML 모델(ECAPA-TDNN 등) 입력 벡터로 활용 예정.

#### 5. Speaking Rate (발화 속도)

정의: 초당 음절 수를 에너지 피크로 근사 추정.

```
1. 프레임 단위 RMS 계산
2. 임계값 = mean(RMS) × 0.5
3. RMS 시계열에서 극대값(peak) 카운트
4. Speaking Rate = peak 수 / 발화 시간(초)
```

기준값 (한국어 자연 발화):

| 범위 | 해석 |
|------|------|
| < 2.5 onset/s | 느림 → sad / calm |
| 2.5–4.0 onset/s | 보통 → neutral / calm |
| > 4.0 onset/s | 빠름 → excited / happy |

---

### Audio Branch — 분류 규칙 (Rule Engine)

추출된 특징을 아래 규칙에 대입하여 각 감정 클래스에 가중치를 누적한 뒤 L1 정규화:

```
초기값: neutral = 0.10 (베이스라인)

# F0=0 폴백: 자기상관이 유성음을 감지하지 못한 경우(F0 < 50Hz)
# f0_mean = 150.0, f0_std = 25.0 으로 기본값 사용 (RMS/ZCR이 감정 결정)

R1: f0 > 185Hz AND rms > 0.06 AND rate > 3.5
    → excited += 0.55, happy += 0.20   # 고음+큰소리+빠름 = 흥분

R2: f0 > 155Hz AND rms > 0.04  (R1에 해당 안 될 때)
    → happy += 0.45, excited += 0.10   # 중간 이상 피치+에너지 = 행복

R3: rms > 0.07 AND (zcr > 0.12 OR f0_std > 35Hz)
    → angry += 0.50                    # 큰소리+마찰음 또는 불규칙 피치 = 분노

R4: f0 < 140Hz AND rms < 0.05 AND rate < 3.0
    → sad += 0.45                      # 낮은음+작은소리+느림 = 슬픔

R5: rms < 0.06 AND f0_std < 28Hz AND 2.0 < rate < 4.5
    → calm += 0.35                     # 조용+단조로움+보통속도 = 차분

R6: rms < 0.03
    → calm += 0.25                     # 매우 조용한 경우 = 차분

R7: rate > 4.5 AND rms > 0.05
    → excited += 0.20, happy += 0.10   # 빠른 발화 = 흥분/행복

최종: L1 정규화 → sum(probs) = 1.0
      emotion = argmax(probs)
      intensity = max(probs)  ∈ [0.0, 1.0]
```

> 규칙이 중복 적용될 수 있음: 예를 들어 매우 큰 소리(R3)이면서 높은 피치(R2)인 경우, angry와 happy 양쪽에 가중치가 붙고 정규화 후 더 높은 쪽으로 결정됨.

---

### Text Branch — 텍스트 감정 분석

STT로 변환된 텍스트에서 감정 키워드를 카운팅하는 이중 언어(KO/EN) 렉시콘 방식.

```
각 감정별 키워드 등장 횟수 카운트 → L1 정규화

예시:
  "오늘 너무 기뻐요" → happy += 2 (기뻐, 너무→암묵적 강조)
  "I'm so excited!"  → excited += 1
```

한국어 키워드 예시:

| 감정 | 키워드 |
|------|--------|
| happy | 기뻐, 기쁘, 좋아, 행복, 감사, 웃, 즐거, 신나, 사랑 |
| sad | 슬프, 우울, 힘들, 외로, 눈물, 그리워, 괴로, 아프 |
| angry | 화나, 짜증, 열받, 싫어, 분노, 억울, 황당 |
| excited | 흥분, 설레, 두근, 기대, 와우, 대박, 놀라 |
| calm | 평온, 차분, 괜찮, 안정, 편안, 조용 |

> 텍스트가 없거나 매칭 키워드가 없으면 neutral 베이스라인(0.10)만 적용.

---

### Fusion — 두 브랜치 결합

```
p_fused[c] = 0.6 × p_audio[c] + 0.4 × p_text[c]

→ L1 정규화
→ emotion = argmax(p_fused)
→ intensity = max(p_fused)
```

가중치 선택 이유:
- 오디오 특징이 감정의 비언어적 신호(목소리 떨림, 속도, 높낮이)를 직접 반영하므로 더 높은 비중(0.6)
- 텍스트는 명시적 감정 표현만 잡아내므로 보조 역할(0.4)
- 텍스트가 없으면 오디오 결과만 사용

Intensity 해석:

| 값 | 의미 |
|----|------|
| > 0.70 | 강하고 명확한 감정 |
| 0.40–0.70 | 보통 |
| < 0.40 | 약함 / 모호 (neutral 방향) |

---

### Prosody 후처리 — 감정별 TTS 조정

분석된 감정을 TTS 음성에 반영하기 위해 scipy로 오디오를 변형:

```
rate'   = 1.0 + (rate_target  - 1.0) × intensity  → scipy resample_poly
pitch'  = pitch_target × intensity                  → 리샘플 + 원본 길이 복원
energy' = 1.0 + (energy_target - 1.0) × intensity  → 진폭 스케일
```

| 감정 | 속도(rate) | 피치(semitone) | 에너지 |
|------|:----------:|:--------------:|:------:|
| neutral | 1.00 | 0.0 | 1.00 |
| happy | 1.10 | +2.0 | 1.20 |
| sad | 0.85 | -3.0 | 0.80 |
| angry | 1.15 | +1.0 | 1.40 |
| excited | 1.20 | +4.0 | 1.30 |
| calm | 0.90 | -1.0 | 0.90 |

---

## 기술 스택

| 컴포넌트 | 선택 | 이유 |
|----------|------|------|
| 프레임워크 | FastAPI | 비동기, WebSocket, OpenAPI 자동 생성 |
| VAD | silero-vad | 5–15ms, 추가 패키지 없음, graceful fallback |
| STT | faster-whisper tiny (서브프로세스) | SIGABRT 방지, 경량, 한국어 지원 |
| 감정 (오디오) | numpy + scipy prosody | GPU 불필요, 완전 해석 가능 |
| 감정 (텍스트) | 키워드 렉시콘 KO+EN | 의존성 없음, KoBERT 업그레이드 경로 명확 |
| LLM | Ollama → Anthropic API → 템플릿 | 로컬 우선, 멀티턴 대화 히스토리 |
| TTS | macOS say (Yuna, ko_KR) | 한국어 내장, 200–500ms, 목소리 선택 가능 |
| 스트리밍 | WebSocket JSON+base64 | 저지연, 양방향 |
| 프론트엔드 | Next.js 14 + Tailwind + Framer Motion | 대화형 UI, 감정별 동적 색상 |

---

현재 가능한 기능                                                                                          
                                                                                                            
  핵심 파이프라인                                                                                           
                                                                                                            
  ┌───────────────────┬─────────────────────────────────────────────────────┬──────┐                        
  │       단계        │                        기술                         │ 상태 │                        
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤                        
  │ 마이크 녹음       │ MediaRecorder + WebSocket                           │ ✅   │                        
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤
  │ 음성 감지 (VAD)   │ silero-vad, 5–15ms                                  │ ✅   │                        
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤                        
  │ 음성→텍스트 (STT) │ faster-whisper tiny, 한국어/영어 자동감지           │ ✅   │                        
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤                        
  │ 감정 분석         │ F0+RMS+ZCR+MFCC+발화속도 룰엔진, 텍스트 키워드 융합 │ ✅   │                        
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤                        
  │ AI 응답 생성      │ Ollama → Claude API → 템플릿 폴백                   │ ✅   │
  ├───────────────────┼─────────────────────────────────────────────────────┼──────┤
  │ 음성 합성 (TTS)   │ macOS say (Yuna 등), prosody 후처리                 │ ✅   │
  └───────────────────┴─────────────────────────────────────────────────────┴──────┘

  UI/UX

  - 대화 버블 히스토리 (사용자/AI 구분)
  - 오디오 재생 완료 후 자동으로 다음 발화 대기 전환
  - 감정 분석 카드가 2번째 턴부터 계속 유지
  - 감정별 색상/이모지/확률 바 실시간 표시
  - VAD 신뢰도 실시간 바
  - 레이턴시 측정 (VAD/STT/감정/TTS 별도)
  - 음성 종류 선택 드롭다운
  - 오디오 파일 업로드 (REST 모드)
  - 라이트 모드 UI

  성능 (macOS M1 CPU)

  - 2초 발화 기준 전체 왕복: ~650ms

  ---
  앞으로 가능한 계획

  단기 (기술적으로 준비됨)

  ┌────────────────────┬────────────────────────────────────────────────────────────────────────────┐
  │        항목        │                                    내용                                    │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────┤
  │ Ollama 연동        │ brew install ollama && ollama pull llama3.2 하면 즉시 로컬 LLM 대화 활성화 │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────┤
  │ Claude API 연동    │ ANTHROPIC_API_KEY 설정하면 Claude Haiku로 실제 대화 가능                   │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────┤
  │ whisper small 전환 │ .env에서 WHISPER_MODEL_SIZE=small 변경 → STT 정확도 향상                   │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────┤
  │ 다양한 TTS 음성    │ macOS 설치된 모든 음성 자동 감지, UI에서 바로 선택 가능                    │
  └────────────────────┴────────────────────────────────────────────────────────────────────────────┘

  중기 (ML 모델 교체)

  ┌─────────────┬───────────────┬────────────────────────────────┐
  │    항목     │     현재      │              목표              │
  ├─────────────┼───────────────┼────────────────────────────────┤
  │ 감정 오디오 │ 규칙 엔진     │ ECAPA-TDNN (SER 모델)          │
  ├─────────────┼───────────────┼────────────────────────────────┤
  │ 감정 텍스트 │ 키워드 렉시콘 │ klue/roberta fine-tuned        │
  ├─────────────┼───────────────┼────────────────────────────────┤
  │ 한국어 TTS  │ macOS say     │ XTTS v2 (GPU) 또는 한국어 VITS │
  └─────────────┴───────────────┴────────────────────────────────┘

  장기 (시스템 확장)

  - 실시간 스트리밍 STT (발화 중 부분 텍스트 표시)
  - 화자 분리 (여러 명이 대화해도 구분)
  - 감정 변화 시계열 차트 (대화 흐름 시각화)
  - 배포 (Vercel + Railway or Docker Compose)


## 설치 및 실행

### 백엔드

```bash
cd backend
pip install -r requirements.txt

# macOS — 반드시 아래 환경변수와 함께 실행
KMP_DUPLICATE_LIB_OK=TRUE HF_HUB_OFFLINE=1 \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> macOS에서 `KMP_DUPLICATE_LIB_OK=TRUE` 없이 실행하면 CTranslate2 + OpenMP 충돌로 SIGABRT 발생.
> 상세 내용: [reports/TROUBLESHOOTING.md](reports/TROUBLESHOOTING.md)

```
http://localhost:8000/docs    Swagger UI
http://localhost:8000/health  상태 확인
```

### 프론트엔드

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

### LLM 대화 활성화 (선택)

```bash
# 옵션 1: Ollama 로컬 LLM (무료)
brew install ollama
ollama serve &
ollama pull llama3.2

# 옵션 2: Anthropic Claude API
export ANTHROPIC_API_KEY=sk-ant-...
```

둘 다 없으면 감정 기반 템플릿 응답으로 자동 폴백.

---

## 레이턴시 (macOS Apple M1, CPU-only, say TTS)

| 입력 | VAD | STT (tiny) | 감정 | TTS (say) | 합계 |
|------|:---:|:----------:|:----:|:---------:|:----:|
| 2초 | 10ms | 180ms | 60ms | 400ms | **~650ms** |
| 5초 | 20ms | 300ms | 80ms | 500ms | **~900ms** |

상세 측정: [reports/latency_benchmark.md](reports/latency_benchmark.md)

---

## 리포지토리 구조

```
/
├── backend/
│   ├── stt_worker_process.py         STT 격리 서브프로세스
│   └── app/
│       ├── main.py                   FastAPI 진입점
│       ├── config.py                 환경 설정
│       ├── api/
│       │   ├── routes.py             HTTP 엔드포인트
│       │   └── websocket.py          WS /ws/voice 파이프라인
│       ├── services/
│       │   ├── audio_io.py           오디오 로드/변환
│       │   ├── vad_service.py        silero-vad
│       │   ├── stt_service.py        faster-whisper 클라이언트
│       │   ├── emotion_service.py    특징 추출 + 분류 + 융합
│       │   ├── llm_service.py        LLM 대화 (Ollama/Claude/템플릿)
│       │   ├── response_generator.py 감정 기반 템플릿
│       │   └── tts_service.py        TTS + prosody 후처리
│       └── models/
│           └── emotion_classifier.py 규칙 분류기 (교체 가능 인터페이스)
├── frontend/
│   └── src/
│       ├── app/                      Next.js App Router
│       ├── components/               UI 컴포넌트
│       ├── hooks/useVoicePipeline.ts WebSocket 훅
│       └── types/pipeline.ts         TypeScript 타입
└── reports/
    ├── model_choices.md              모델/엔진 선택 근거
    ├── latency_benchmark.md          레이턴시 측정 결과
    ├── TROUBLESHOOTING.md            오류와 해결 과정
    └── EXPERIMENT_TEMPLATE.md        실험 보고서 템플릿
```

---

## 라이선스

MIT
