# 트러블슈팅 기록

> macOS (Apple Silicon / Intel) 환경에서 발생한 주요 오류와 해결 과정

---

## 1. librosa / numba 빌드 실패

### 증상
```
pip install librosa → numba requires llvmlite → llvmlite build failed
ERROR: Failed building wheel for llvmlite
```

### 원인
`librosa 0.9+`는 `numba`를 hard dependency로 요구하고, `numba`는 `llvmlite`를, `llvmlite`는 로컬 LLVM 헤더를 필요로 한다. macOS에 LLVM 개발 도구가 없으면 빌드 실패.

### 해결
`librosa`를 완전히 제거하고 `numpy` / `scipy`만으로 재구현.

| 대체 | librosa 함수 | 순수 numpy/scipy 구현 |
|------|-------------|----------------------|
| F0 추출 | `librosa.pyin` | 자기상관(autocorrelation) 기반 직접 구현 |
| 리샘플링 | `librosa.resample` | `scipy.signal.resample_poly` + `math.gcd` |
| MFCC | `librosa.feature.mfcc` | DCT 행렬 곱 + `scipy.fft.fft` |
| Prosody 후처리 | `librosa.effects.time_stretch` | `scipy.signal.resample_poly` 근사 |

관련 파일: `backend/app/services/emotion_service.py`, `audio_io.py`, `tts_service.py`

---

## 2. numpy 2.x vs torch 2.2.2 비호환

### 증상
```
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.2
```
torch가 numpy 2.x에서 import 직후 crash.

### 원인
`torch 2.2.2`는 numpy 1.x API로 컴파일되었으나, pip가 numpy 2.2.6을 설치함.

### 해결
```bash
pip3 install "numpy<2"   # → numpy 1.26.4 설치
```

---

## 3. config.py 최상위 `import torch` — 서버 시작 실패

### 증상
서버 시작 시 torch가 설치되지 않은 환경에서 즉시 crash.

### 원인
`DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"` 가 모듈 최상위에서 실행됨.

### 해결
```python
# Before
DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

# After
def _detect_device() -> str:
    try:
        import torch          # lazy import
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

DEVICE: str = _detect_device()
```
이후 macOS OpenMP 충돌 문제 해결을 위해 `DEVICE: str = "cpu"` 하드코딩으로 변경.

---

## 4. 파이썬 예기치 종료 팝업 (SIGABRT) — 핵심 문제

### 증상
- macOS "Python이 예기치 않게 종료되었습니다" 팝업이 반복적으로 표시됨
- 서버 로그: `STT: loading whisper-tiny device=cpu compute=int8` 직후 프로세스 종료
- 브라우저에 WebSocket 연결 오류 발생

### 원인 분석 과정

Step 1: `vad_service.py` 최상위 `import torch` 제거 → 여전히 crash
Step 2: `KMP_DUPLICATE_LIB_OK=TRUE` 환경변수 외부 설정 → 여전히 crash
Step 3: `HF_HUB_OFFLINE=1` 없이 테스트 → OMP Error #15, exit code 134 확인
Step 4: 독립 Python 스크립트에서 whisper-tiny 테스트 → 정상 작동

```
Loading...
Transcribing...
OK - lang: ko   ← 독립 실행 시 완벽하게 동작
```

Step 5: uvicorn 내부에서만 crash 확인 → asyncio 이벤트 루프와 CTranslate2 충돌 진단

### 근본 원인
CTranslate2 (faster-whisper의 내부 엔진)는 자체 스레드 풀과 OpenMP 런타임을 초기화한다. uvicorn의 asyncio 이벤트 루프 스레드에서 CTranslate2를 직접 초기화하면, 두 런타임의 스레드 관리 방식이 충돌하여 SIGABRT (exit 134)가 발생한다. macOS 특정 현상.

### 해결책
STT를 완전히 별도의 서브프로세스로 격리

```
[uvicorn 프로세스]                    [stt_worker_process.py]
  asyncio event loop                  독립 Python 프로세스
  FastAPI handler                     CTranslate2 로드
       │                                    │
       │── stdin: JSON (audio_b64) ─────────▶│
       │◀────── stdout: JSON (결과) ─────────│
```

`stt_worker_process.py`: stdin/stdout 파이프로 통신하는 영구 워커 프로세스.
`stt_service.py`: `subprocess.Popen`으로 워커를 기동하고, 라인 단위 JSON으로 오디오를 전송하고 결과를 수신.

결과: HTTP 200 응답, 서버 크래시 없음 ✅

### 부수적으로 발견된 문제
워커 스크립트를 `backend/app/utils/` 안에 두면, Python이 스크립트 디렉토리를 `sys.path`에 추가해서 같은 디렉토리의 `logging.py`가 표준 라이브러리 `logging`을 shadow함 → `av` 라이브러리 import 실패.

해결: 워커 스크립트를 `backend/stt_worker_process.py` (루트)로 이동.

---

## 5. afconvert 오버헤드 (TTS 느림)

### 증상
macOS `say` TTS 엔진이 AIFF를 생성한 뒤 WAV로 변환하는 `afconvert` subprocess를 별도로 실행해 불필요한 지연 발생.

### 해결
`soundfile` 라이브러리는 AIFF를 네이티브로 읽을 수 있으므로 `afconvert` 단계를 완전 제거.

```python
# Before
subprocess.run(["say", "-o", aiff_path, text])
subprocess.run(["afconvert", aiff_path, wav_path, "-f", "WAVE"])  # 제거
audio, sr = sf.read(wav_path)

# After
subprocess.run(["say", "-v", voice, "-r", "200", "-o", aiff_path, text])
audio, sr = sf.read(aiff_path, dtype="float32")  # AIFF 직접 읽기
```

---

## 6. 스타트업 이벤트에서 모델 프리워밍 crash

### 증상
`@app.on_event("startup")`에서 `asyncio.to_thread()` / `run_in_executor()`로 WhisperModel 로드 시 서버 시작 직후 crash.

### 원인
asyncio startup 이벤트 핸들러 내에서 파생된 스레드가 HuggingFace Hub API에 httpx 비동기 요청을 보내려 할 때 이벤트 루프 상태와 충돌. 모델 다운로드 중 XetHub 프로토콜과 asyncio httpx 클라이언트 충돌.

### 해결
스타트업 프리워밍 완전 제거. 첫 번째 요청 시 lazy loading으로 처리. (워커 서브프로세스 방식으로 전환 후 이 문제 자체가 해소됨)

---

## 7. LLM 응답 — 정해진 대답만 나오는 경우

### 증상
AI가 "감사합니다, 기분이 좋아 보여요!" 같은 고정된 템플릿 응답만 반환함.

### 원인
Ollama가 설치되지 않고 `ANTHROPIC_API_KEY`도 설정되지 않은 경우, `llm_service.py`가 자동으로 `response_generator.py` 템플릿 폴백으로 동작함.

### 해결 — 옵션 1: Ollama 로컬 LLM

```bash
brew install ollama
ollama serve &              # 백그라운드 실행
ollama pull qwen2.5:1.5b   # 모델 다운로드 (~1GB, 한국어 최적)
```

이후 서버 재시작하면 자동으로 Ollama를 사용.

### 해결 — 옵션 2: Anthropic Claude API

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`llm_service.py`가 Claude Haiku를 사용하여 멀티턴 대화 생성.

---

## 환경 설정 요약 (안정적으로 서버 기동하는 방법)

```bash
cd backend
export KMP_DUPLICATE_LIB_OK=TRUE   # OpenMP 중복 로드 경고 억제
export HF_HUB_OFFLINE=1            # HuggingFace 네트워크 요청 스킵 (캐시 사용)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

또는 `nohup` 백그라운드 실행:
```bash
KMP_DUPLICATE_LIB_OK=TRUE HF_HUB_OFFLINE=1 \
  nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/server.log 2>&1 &
```

서버 시작 시 STT 워커 + Ollama 모델이 자동으로 사전 로드됨 (startup 이벤트).
첫 번째 요청부터 STT 및 LLM 지연 없이 처리 가능.

---

## 8. STT 트랜스크립트 항상 비어있음 (WebM 청크 Race Condition)

### 증상
- 서버 로그에 `transcript: ''` 가 지속적으로 출력됨
- 음성을 녹음해도 AI 응답이 없거나 TTS만 0.1초 짧게 출력됨
- RTF(Real-Time Factor) 12–42x 로 비정상적으로 높음

### 원인 분석

이전 구현 방식:
```
MediaRecorder → 500ms마다 ondataavailable → WebM 청크 → ArrayBuffer → decodeAudioData(청크별) → base64 → WS 전송
→ stop 호출 직후 end_stream 전송
```

문제: WebM/Opus는 연속적인 스트림 포맷이다. 개별 500ms 청크는 각각 WebM 헤더를 가지고 있지 않아 `decodeAudioData`가 각 청크를 독립적으로 디코딩하려 하면 실패한다. 또한 `decodeAudioData`는 비동기 작업이므로, `recorder.stop()` 직후에 `end_stream`을 보내면 서버가 `end_stream`을 먼저 수신하고 빈 오디오 버퍼로 처리한다.

```
[클라이언트]              [서버]
recorder.stop()
          → (async청크 디코딩 중...)
          → end_stream 전송  ← 이 시점에 서버 도착
                              ← audio_buffer: []
                              ← transcript: ''  ← 빈 버퍼
          → audio_chunk 전송  ← 이미 처리됨, 무시
```

### 해결

새 구현 방식: 모든 Blob을 누적한 뒤 하나의 완전한 WebM 파일로 합쳐서 디코딩.

```typescript
// 녹음 중: Blob만 누적 (디코딩 X)
recorder.ondataavailable = ({ data }) => {
  if (data.size > 0) blobChunks.current.push(data);
};

// 정지 후: 합쳐서 한번에 디코딩
await new Promise(r => setTimeout(r, 350)); // 마지막 ondataavailable 대기
const combined = new Blob(blobChunks.current, { type: 'audio/webm;codecs=opus' });
const ab = await combined.arrayBuffer();
const dec = await ctx.decodeAudioData(ab);  // 완전한 WebM 파일 디코딩 → 성공
const pcm = dec.getChannelData(0);

ws.send(JSON.stringify({ type: 'audio_chunk', data: float32ToBase64(pcm) }));
ws.send(JSON.stringify({ type: 'end_stream' }));  // 오디오 전송 완료 후 전송
```

결과: transcript가 정상적으로 채워지고 LLM 응답이 음성 내용을 기반으로 생성됨 ✅

---

## 9. 감정이 항상 neutral로 표시됨

### 증상
- 어떤 말을 해도 감정 분석 결과가 항상 `neutral`로 표시됨
- intensity가 낮음 (~0.15–0.20)

### 원인
두 가지 원인:

1. F0 자기상관 실패: 마이크 녹음에서 묵음 프레임 비율이 높아 autocorrelation이 F0=0을 반환. 이 경우 모든 피치 기반 규칙(R1, R2, R4)이 발동되지 않고 `neutral` 베이스라인(0.15)이 우세.

2. 임계값이 과도하게 엄격: 원래 임계값은 녹음실 수준 음성을 기준으로 설정됨. 실제 마이크 입력은 그보다 낮은 RMS, F0를 가짐.

### 해결

```python
# 1. F0=0 폴백 처리
f0_reliable = f0_mean > 50.0
if not f0_reliable:
    f0_mean = 150.0   # 기본 피치 가정; RMS/ZCR이 감정 결정
    f0_std  = 25.0

# 2. 임계값 완화
# R1: f0>185 (210→), rms>0.06 (0.08→), rate>3.5 (4.0→)
# R2: f0>155 (175→), rms>0.04 (0.055→)
# R3: rms>0.07 (0.09→), zcr>0.12 OR f0_std>35 (AND → OR)
# R4: f0<140 (130→), rms<0.05 (0.04→), rate<3.0 (2.5→)
# R5: rms<0.06, f0_std<28, 2.0<rate<4.5

# 3. 새 규칙 추가
# R6: rms<0.03 → calm (아주 조용한 경우)
# R7: rate>4.5 AND rms>0.05 → excited/happy (빠른 발화)

# 4. neutral 베이스라인 낮춤
probs["neutral"] = 0.10  # 0.15 → 0.10
```

결과: 실제 마이크 입력에서 감정이 다양하게 감지됨 ✅

---

## 10. macOS 브라우저 WebAudio — 무음 PCM 생성 버그

### 증상
- 마이크를 말해도 서버 로그에 `rms=0.00009` (사실상 무음)
- macOS 시스템 설정 → 사운드 → 입력에서는 8칸까지 레벨이 정상 표시
- `transcript: ''` 또는 `transcript: '오,,,,,,,,,,,,,,,,'` (garbage)
- 외부 기기(핸드폰 마이크 등)로는 정상 동작

### 원인
macOS에서 `AudioContext({ sampleRate: 16000 })`로 컨텍스트를 생성하면, `decodeAudioData`가 내부적으로 오디오를 16kHz로 리샘플링하는 과정에서 사실상 무음 신호를 생성한다. 이는 macOS + Chrome 조합의 WebAudio API 구현 버그로 추정된다.

```typescript
// 문제 코드
const ctx = new AudioContext({ sampleRate: 16000 });
const dec = await ctx.decodeAudioData(ab);
// dec.getChannelData(0) → rms≈0.0001 (무음)
```

### 해결

브라우저에서 WebAudio 디코딩을 완전히 포기하고, raw WebM을 서버에서 ffmpeg으로 디코딩하는 방식으로 전환.

**Frontend (`useVoicePipeline.ts`)**:
```typescript
// 모든 Blob 누적 후 base64로 인코딩, encoding:'webm' 필드와 함께 전송
const combined = new Blob(blobChunks.current, { type: 'audio/webm;codecs=opus' });
const ab = await combined.arrayBuffer();
const bytes = new Uint8Array(ab);
let bin = '';
for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
const b64 = btoa(bin);
ws.send(JSON.stringify({ type: 'audio_chunk', data: b64, encoding: 'webm' }));
```

**Backend (`websocket.py`)**:
```python
def _ffmpeg_decode(webm_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    proc = subprocess.run(
        ['ffmpeg', '-y', '-i', 'pipe:0', '-f', 'f32le', '-ar', str(target_sr), '-ac', '1', 'pipe:1'],
        input=webm_bytes, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.decode()[:400]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
```

결과: rms가 정상 범위(0.05~0.2)로 복구, STT 정상 작동 ✅

---

## 11. Ollama 첫 응답 60초+ 지연

### 증상
- 서버 시작 후 첫 번째 LLM 요청에서 `httpx.ReadTimeout` 발생
- 20초, 60초 timeout을 설정해도 여전히 실패

### 원인
Ollama가 서버에 로드되어 있지 않을 때 첫 번째 API 요청이 모델 로딩 + 프롬프트 평가 + 생성을 모두 처리해야 한다. qwen2.5:1.5b 모델이 CPU에서 로드되는 시간이 30~90초로, 기본 timeout을 초과한다.

### 해결

1. **서버 startup 워밍업**: 백엔드 시작 시 짧은 메시지로 모델을 미리 로드

```python
@app.on_event("startup")
async def _warmup_ollama():
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "http://localhost:11434/api/chat",
            json={"model": "qwen2.5:1.5b", "messages": [{"role":"user","content":"안녕"}],
                  "stream": False, "keep_alive": -1, "options": {"num_predict": 20}},
        )
```

2. **keep_alive: -1**: 모델을 메모리에 영구 상주 (Ollama 기본값은 5분 후 언로드)

3. **timeout 90s**: 워밍업 실패해도 앱은 시작되도록 try/except로 처리

결과: 워밍업 후 두 번째 요청부터 5~15초 내에 응답 ✅

---

## 12. Ollama 한국어 응답에 영어/한자/베트남어 혼용

### 증상
- `llama3.2`, `llama3.2:1b` 사용 시 한국어 응답 중간에 영어, 베트남어, 중국 한자 혼입
- system prompt에 "한국어로만" 지시해도 효과 없음

### 원인
`llama3.2` 시리즈는 Meta의 multilingual 모델로, 짧은 한국어 context에서 언어 스위칭이 빈번하다. `num_predict`를 낮게 제한할수록 불완전한 문장에서 언어 혼용이 심해진다.

### 해결

`qwen2.5:1.5b`로 전환 — Alibaba의 한국어 지원에 특화된 1.5B 경량 모델.

```bash
ollama pull qwen2.5:1.5b
```

System prompt에 명시적 언어 제한 강화:
```python
_SYSTEM_PROMPT = (
    "당신은 따뜻하고 공감 능력이 뛰어난 AI 음성 어시스턴트입니다. "
    "반드시 한국어로만 답변하세요. 영어, 한자, 다른 언어는 절대 사용하지 마세요. "
    ...
)
```

결과: 한국어 전용 응답 안정적으로 생성됨 ✅

---

## 13. qwen2.5:1.5b 한국어 응답에 漢字 누출

### 증상
- qwen2.5:1.5b로 전환 후에도 한국어 응답에 中文 한자가 섞여 출력됨
- 예: `못忍受하는 거예요`, `放松하고 싶어요`, `聊聊 해요`
- system prompt에 "한자 사용 금지" 명시해도 모델 레벨에서 완전히 차단 불가

### 원인
qwen2.5는 Alibaba의 중국어 학습 데이터 비중이 높아, 한국어 응답 생성 시 CJK 문자를 섞는 경향이 있다. 특히 짧은 컨텍스트에서 `num_predict` 제한이 있을 때 불완전한 토큰 완성 과정에서 한자가 누출된다.

### 해결

LLM 응답 후 CJK 유니코드 범위를 정규식으로 제거하는 후처리 함수 추가:

```python
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')

def _clean_response(text: str, reply_language: str) -> str:
    if reply_language in ("ko", "en"):
        text = _CJK_RE.sub('', text)
        text = re.sub(r'  +', ' ', text).strip()
    return text
```

- 한국어(`ko`), 영어(`en`) 응답에만 적용 (일본어, 중국어 응답은 통과)
- 제거 후 다중 공백을 단일 공백으로 정리

결과: 한국어/영어 응답에서 한자 누출 완전 제거 ✅

---

## 14. DuckDuckGo 검색 태그가 AI 응답에 그대로 출력됨

### 증상
- 감정적 대화 중에도 `[검색 결과]` 태그 문자열이 AI 응답에 그대로 출력됨
- 예: "오늘 힘들었어" → AI: `[검색 결과] ... 힘드셨군요`
- 응답 품질 저하 및 부자연스러운 대화 흐름

### 원인
DuckDuckGo Instant Answer API 호출 결과를 `[검색 결과]` 태그로 LLM 컨텍스트에 주입했을 때, qwen2.5:1.5b가 태그 자체를 응답에 포함시키는 경향이 있었다. 또한 DDG 검색이 감정 대화 키워드에도 발동되어 무관한 검색 결과가 주입되었다.

### 해결

DuckDuckGo 검색을 완전히 비활성화하고, 날씨 검색만 유지:

```python
async def search_if_needed(query: str) -> Optional[str]:
    if _WEATHER_KW.search(query):
        result = await fetch_weather(query)
        if result:
            return f"[실시간 날씨] {result}"
    return None  # DDG 검색 비활성화
```

날씨 검색은 Open-Meteo API를 사용하며, 실측 구조화 데이터이므로 LLM이 태그 없이 자연스럽게 변환한다.

결과: 태그 오염 없이 날씨 쿼리에만 검색 결과 주입 ✅
