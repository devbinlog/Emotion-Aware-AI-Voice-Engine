# Experiment Report Template

> Copy this file for each experiment. Name: `exp_YYYYMMDD_<topic>.md`

---

## 1. Objective

> One sentence: what hypothesis or question are we testing?

**Example**: "Does switching from Coqui VITS to Piper ONNX reduce TTS latency below 300ms on CPU without perceptible quality degradation?"

---

## 2. Environment

| Field               | Value |
|---------------------|-------|
| Date                |       |
| OS / CPU            |       |
| GPU (if any)        |       |
| Python version      |       |
| Key lib versions    |       |
| TTS engine          |       |
| Whisper model       |       |
| Emotion classifier  |       |

---

## 3. Data / Stimuli

| Field          | Description |
|----------------|-------------|
| Language       | KO / EN / mixed |
| # samples      |       |
| Duration range | e.g. 2–10s |
| Emotion labels | ground-truth available? |
| Noise level    | clean / SNR XX dB |
| Source         | internal recording / public dataset |

---

## 4. Method

> Step-by-step protocol. Include any random seeds, model config changes.

1.
2.
3.

---

## 5. Results

### 5a. Latency (ms)

| Stage       | Baseline p50 | Experiment p50 | Delta |
|-------------|:------------:|:--------------:|:-----:|
| VAD         |              |                |       |
| STT         |              |                |       |
| Emotion     |              |                |       |
| TTS         |              |                |       |
| **Total**   |              |                |       |

### 5b. Emotion Classification (if applicable)

| Emotion   | Precision | Recall | F1 |
|-----------|:---------:|:------:|:--:|
| neutral   |           |        |    |
| happy     |           |        |    |
| sad       |           |        |    |
| angry     |           |        |    |
| excited   |           |        |    |
| calm      |           |        |    |
| **macro** |           |        |    |

### 5c. TTS Quality (if applicable)

| Metric                   | Score |
|--------------------------|-------|
| MOS (subjective, N=?)    |       |
| UTMOS (automated)        |       |
| WER round-trip (TTS→STT) |       |

---

## 6. Observations

> Free-form notes on unexpected behavior, failure modes, edge cases.

---

## 7. Conclusion

- Hypothesis confirmed / rejected / partially supported?
- Key finding in one sentence:

---

## 8. Next Actions

- [ ] Action 1
- [ ] Action 2
