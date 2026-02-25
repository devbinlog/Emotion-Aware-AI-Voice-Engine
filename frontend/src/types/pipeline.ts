export type EmotionLabel = 'neutral' | 'happy' | 'sad' | 'angry' | 'excited' | 'calm';
export type PipelineStage = 'vad' | 'stt' | 'emotion' | 'tts';
export type PipelineStatus = 'idle' | 'recording' | 'processing' | 'playing' | 'error';

export interface Segment {
  start: number;
  end: number;
  text: string;
  confidence: number;
}

export interface FeaturesSummary {
  f0_mean:       number;
  f0_std:        number;
  rms_mean:      number;
  zcr_mean:      number;
  speaking_rate: number;
}

export interface EmotionResult {
  emotion_label:    EmotionLabel;
  intensity:        number;
  probabilities:    Record<EmotionLabel, number>;
  features_summary: FeaturesSummary;
}

export interface PipelineMetrics {
  vad_ms:     number;
  stt_ms:     number;
  emotion_ms: number;
  tts_ms:     number;
  total_ms:   number;
  rtf?:       number;
}

export interface PipelineState {
  status:        PipelineStatus;
  stage:         PipelineStage | null;
  transcript:    string;
  aiResponse:    string;        // AI-generated response text
  emotion:       EmotionResult | null;
  metrics:       PipelineMetrics | null;
  audioUrl:      string | null;
  vadConfidence: number;
  error:         string | null;
}

// ── Visual config per emotion ──────────────────────────────────────────────
export const EMOTION_CONFIG: Record<EmotionLabel, {
  emoji:   string;
  label:   string;
  primary: string;
  dim:     string;
  glow:    string;
}> = {
  neutral: { emoji: '😐', label: '중립',  primary: '#94a3b8', dim: 'rgba(148,163,184,0.12)', glow: 'rgba(148,163,184,0.3)' },
  happy:   { emoji: '😊', label: '행복',  primary: '#fbbf24', dim: 'rgba(251,191,36,0.12)',  glow: 'rgba(251,191,36,0.35)' },
  sad:     { emoji: '😢', label: '슬픔',  primary: '#60a5fa', dim: 'rgba(96,165,250,0.12)',  glow: 'rgba(96,165,250,0.35)' },
  angry:   { emoji: '😠', label: '분노',  primary: '#f87171', dim: 'rgba(248,113,113,0.12)', glow: 'rgba(248,113,113,0.35)' },
  excited: { emoji: '🤩', label: '흥분',  primary: '#c084fc', dim: 'rgba(192,132,252,0.12)', glow: 'rgba(192,132,252,0.35)' },
  calm:    { emoji: '😌', label: '차분',  primary: '#34d399', dim: 'rgba(52,211,153,0.12)',  glow: 'rgba(52,211,153,0.35)' },
};

export const PIPELINE_STAGES: { key: PipelineStage; label: string }[] = [
  { key: 'vad',     label: 'VAD'     },
  { key: 'stt',     label: 'STT'     },
  { key: 'emotion', label: '감정'    },
  { key: 'tts',     label: 'TTS'     },
];
