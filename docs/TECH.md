# 기술 문서 — Emotion-Aware AI Voice Engine

감정 분석 알고리즘, 특징 추출 방법, 분류 규칙, prosody 후처리에 대한 상세 기술 문서.

---

## 감정 클래스

| 라벨 | 한국어 | 음성 특징 |
|------|--------|-----------|
| `neutral` | 중립 | 기본 베이스라인 |
| `happy` | 행복 | 높은 피치, 중간 에너지 |
| `sad` | 슬픔 | 낮은 피치, 낮은 에너지, 느린 속도 |
| `angry` | 분노 | 높은 에너지, 높은 ZCR, 불규칙한 피치 |
| `excited` | 흥분 | 가장 높은 피치+에너지+속도 조합 |
| `calm` | 차분 | 낮은 에너지, 낮은 피치 변화, 규칙적 속도 |

---

## 감정 분석 구조

두 갈래(Audio Branch, Text Branch)를 병렬로 실행한 뒤 가중 합산(Fusion)한다.

```
음성 신호  ──→ Audio Branch ──→ p_audio[6]
                                               ──→ Fusion ──→ 최종 감정
STT 텍스트 ──→ Text Branch  ──→ p_text[6]
```

---

## Audio Branch — 음성 특징 추출

오디오는 16kHz 모노 float32 PCM으로 정규화한 뒤 5가지 특징군을 추출한다.

### 1. F0 (기본 주파수, Fundamental Frequency)

성대가 진동하는 주파수. 목소리의 높낮이를 나타낸다. 단위: Hz.

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

F0=0 폴백: 자기상관이 유성음을 감지하지 못한 경우(F0 < 50Hz), f0_mean = 150Hz, f0_std = 25Hz 기본값을 사용하고 RMS/ZCR이 감정 결정을 주도한다.

---

### 2. RMS (Root Mean Square Energy)

오디오 신호의 평균 진폭 에너지. 목소리의 크기(음량)를 나타낸다.

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

16kHz float32 정규화 기준. 실제 마이크 입력은 0–1 범위로 정규화된 값.

---

### 3. ZCR (Zero Crossing Rate)

신호가 0을 가로지르는 횟수의 비율. 마찰음(ㅅ, ㅈ, ㅊ)이나 흥분·분노 상태에서 증가한다.

```
각 프레임: ZCR = mean(|sign(x[t]) - sign(x[t-1])| / 2)
```

기준값:

| 범위 | 해석 |
|------|------|
| zcr < 0.10 | 낮음 → 유성음 주도, calm / sad |
| 0.10–0.15 | 보통 |
| zcr > 0.15 | 높음 → 마찰음 많음, angry / excited |

---

### 4. MFCC (Mel-Frequency Cepstral Coefficients)

인간의 청각 특성을 모방한 스펙트럼 특징. 13개 계수로 음색과 조음 방식을 압축 표현한다.

추출 과정:

```
1. 프레임 × Hanning 윈도우
2. FFT → 파워 스펙트럼 |X(f)|²
3. Mel 필터뱅크(40개) 적용: Mel 주파수 = 2595·log10(1 + Hz/700)
4. 로그 변환: log(mel_energy)
5. Type-III DCT → MFCC 1~13번 계수
```

현재는 보조 특징으로 저장되며, 향후 ML 모델(ECAPA-TDNN 등) 입력 벡터로 활용 예정.

---

### 5. Speaking Rate (발화 속도)

초당 음절 수를 에너지 피크로 근사 추정한다.

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

## Audio Branch — 분류 규칙 (Rule Engine)

추출된 특징을 규칙에 대입하여 각 감정 클래스에 가중치를 누적한 뒤 L1 정규화한다.

```
초기값: neutral = 0.10 (베이스라인)

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

규칙은 중복 적용될 수 있다. 예를 들어 큰 소리(R3)이면서 높은 피치(R2)인 경우, angry와 happy 양쪽에 가중치가 붙고 정규화 후 더 높은 쪽으로 결정된다.

---

## Text Branch — 텍스트 감정 분석

STT로 변환된 텍스트에서 감정 키워드를 카운팅하는 이중 언어(KO/EN) 렉시콘 방식.

```
각 감정별 키워드 등장 횟수 카운트 → L1 정규화

예시:
  "오늘 너무 기뻐요" → happy += 1 (기뻐 매칭)
  "I'm so excited!"  → excited += 1
```

한국어 키워드:

| 감정 | 키워드 |
|------|--------|
| happy | 기뻐, 기쁘, 좋아, 행복, 감사, 웃, 즐거, 신나, 사랑 |
| sad | 슬프, 우울, 힘들, 외로, 눈물, 그리워, 괴로, 아프 |
| angry | 화나, 짜증, 열받, 싫어, 분노, 억울, 황당 |
| excited | 흥분, 설레, 두근, 기대, 와우, 대박, 놀라 |
| calm | 평온, 차분, 괜찮, 안정, 편안, 조용 |

텍스트가 없거나 매칭 키워드가 없으면 neutral 베이스라인(0.10)만 적용.

향후 교체 대상: KoBERT / klue-bert-base fine-tuned (동일한 return schema 유지).

---

## Fusion — 두 브랜치 결합

```
p_fused[c] = 0.6 × p_audio[c] + 0.4 × p_text[c]

→ L1 정규화
→ emotion = argmax(p_fused)
→ intensity = max(p_fused)
```

가중치 선택 이유:
- 오디오 특징이 감정의 비언어적 신호(목소리 떨림, 속도, 높낮이)를 직접 반영하므로 더 높은 비중 (0.6)
- 텍스트는 명시적 감정 표현만 잡아내므로 보조 역할 (0.4)
- 텍스트가 없으면 오디오 결과만 사용

Intensity 해석:

| 값 | 의미 |
|----|------|
| > 0.70 | 강하고 명확한 감정 |
| 0.40–0.70 | 보통 |
| < 0.40 | 약함 / 모호 (neutral 방향) |

---

## Prosody 후처리 — 감정별 TTS 조정

분석된 감정을 TTS 음성에 반영하기 위해 scipy로 오디오를 변형한다.

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

## WebSocket 프로토콜

```
Client → Server
  { "type": "config",      "language": "ko", "voice": "Yuna", "history": [...] }
  { "type": "audio_chunk", "data": "<base64 float32 PCM>", "sample_rate": 16000 }
  { "type": "end_stream",  "sample_rate": 16000 }

Server → Client
  { "type": "vad_event",        "speech_detected": bool, "confidence": float }
  { "type": "final_transcript", "text": str }
  { "type": "emotion",          "emotion_label": str, "intensity": float, "probabilities": {...} }
  { "type": "ai_response",      "text": str }
  { "type": "audio_chunk",      "data": "<base64 WAV>", "is_last": bool }
  { "type": "metrics",          "vad_ms": f, "stt_ms": f, "emotion_ms": f, "tts_ms": f }
  { "type": "error",            "message": str }
```

---

## 감정 분류기 교체 방법

`backend/app/models/emotion_classifier.py`의 `EmotionClassifier.classify_audio` 또는 `classify_text`를 오버라이드한다. 동일한 return schema가 필요하다:

```python
{
  "emotion_label": str,           # LABELS 중 하나
  "intensity": float,             # 0.0 – 1.0
  "probabilities": Dict[str, float]  # sum ≈ 1.0
}
```

오디오 브랜치 교체 대상: ECAPA-TDNN, SpeechBrain SER 모델
텍스트 브랜치 교체 대상: KoBERT, klue/roberta-base fine-tuned on MAST/KEmotionBERT
