'use client';

import { motion } from 'framer-motion';
import type { PipelineMetrics } from '@/types/pipeline';

interface Props {
  metrics:     PipelineMetrics | null;
  accentColor: string;
}

const CHIPS = [
  { key: 'vad_ms'     as const, label: 'VAD',  color: '#34d399' },
  { key: 'stt_ms'     as const, label: 'STT',  color: '#60a5fa' },
  { key: 'emotion_ms' as const, label: '감정', color: '#c084fc' },
  { key: 'tts_ms'     as const, label: 'TTS',  color: '#fbbf24' },
];

export default function MetricsPanel({ metrics, accentColor }: Props) {
  if (!metrics) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="flex flex-wrap items-center gap-2"
    >
      {CHIPS.map(c => (
        <div
          key={c.key}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium"
          style={{
            background:  `${c.color}14`,
            border:      `1px solid ${c.color}28`,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: c.color }} />
          <span style={{ color: c.color }}>{c.label}</span>
          <span className="font-semibold" style={{ color: 'var(--text)' }}>{metrics[c.key]}ms</span>
        </div>
      ))}

      <div
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium ml-auto"
        style={{
          background:  `${accentColor}14`,
          border:      `1px solid ${accentColor}28`,
        }}
      >
        <span className="text-sub">합계</span>
        <span className="font-bold" style={{ color: 'var(--text)' }}>{metrics.total_ms}ms</span>
        {metrics.rtf !== undefined && metrics.rtf > 0 && (
          <span className="text-muted">· RTF {metrics.rtf.toFixed(2)}</span>
        )}
      </div>
    </motion.div>
  );
}
