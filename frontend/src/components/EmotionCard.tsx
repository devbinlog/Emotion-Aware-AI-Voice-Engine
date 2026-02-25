'use client';

import { motion, AnimatePresence } from 'framer-motion';
import type { EmotionResult, EmotionLabel } from '@/types/pipeline';
import { EMOTION_CONFIG } from '@/types/pipeline';

interface Props {
  emotion: EmotionResult | null;
}

const ALL_LABELS: EmotionLabel[] = ['happy', 'excited', 'calm', 'neutral', 'sad', 'angry'];

export default function EmotionCard({ emotion }: Props) {
  const label = emotion?.emotion_label ?? 'neutral';
  const cfg   = EMOTION_CONFIG[label];

  return (
    <AnimatePresence mode="wait">
      {emotion ? (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="w-full rounded-2xl overflow-hidden"
          style={{
            background: `linear-gradient(135deg, ${cfg.primary}14 0%, ${cfg.primary}08 100%)`,
            border: `1px solid ${cfg.primary}28`,
          }}
        >
          <div className="px-5 py-4 flex items-center gap-4">
            {/* Emoji */}
            <motion.span
              key={label}
              initial={{ scale: 0.4, rotate: -20 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 280, damping: 20 }}
              className="text-3xl leading-none shrink-0"
              style={{ filter: `drop-shadow(0 0 12px ${cfg.primary}88)` }}
            >
              {cfg.emoji}
            </motion.span>

            {/* Label + Intensity */}
            <div className="shrink-0">
              <p className="text-xs font-semibold" style={{ color: cfg.primary }}>
                {cfg.label}
              </p>
              <p className="text-2xl font-black leading-none" style={{ color: 'var(--text)' }}>
                {Math.round(emotion.intensity * 100)}
                <span className="text-sm font-normal ml-0.5" style={{ color: 'var(--sub)' }}>%</span>
              </p>
            </div>

            {/* Prob bars — horizontal compact */}
            <div className="flex-1 flex flex-col gap-1.5 min-w-0">
              {ALL_LABELS.map(lbl => {
                const c   = EMOTION_CONFIG[lbl];
                const pct = Math.round((emotion.probabilities[lbl] ?? 0) * 100);
                const isTop = lbl === label;
                return (
                  <div key={lbl} className="flex items-center gap-2">
                    <span className="text-[10px] w-8 shrink-0 text-right"
                          style={{ color: isTop ? c.primary : 'var(--muted)' }}>
                      {c.label}
                    </span>
                    <div className="flex-1 h-[3px] rounded-full overflow-hidden"
                         style={{ background: 'rgba(0,0,0,0.07)' }}>
                      <motion.div
                        className="h-full rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.7, ease: 'easeOut' }}
                        style={{
                          background: isTop
                            ? `linear-gradient(90deg, ${c.primary}, ${c.primary}bb)`
                            : 'rgba(0,0,0,0.15)',
                        }}
                      />
                    </div>
                    <span className="text-[10px] w-7 shrink-0"
                          style={{ color: isTop ? c.primary : 'var(--muted)' }}>
                      {pct}%
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Feature pills */}
            <div className="shrink-0 hidden sm:flex flex-col gap-1.5 text-right">
              {[
                { k: 'F0', v: `${Math.round(emotion.features_summary.f0_mean)}Hz` },
                { k: 'RMS', v: emotion.features_summary.rms_mean.toFixed(3) },
                { k: '속도', v: `${emotion.features_summary.speaking_rate.toFixed(1)}/s` },
              ].map(({ k, v }) => (
                <div key={k}>
                  <span className="text-[9px] text-muted block">{k}</span>
                  <span className="text-[11px] font-semibold text-sub">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
