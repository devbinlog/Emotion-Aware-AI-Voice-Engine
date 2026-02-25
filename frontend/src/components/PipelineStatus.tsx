'use client';

import { motion } from 'framer-motion';
import { PIPELINE_STAGES } from '@/types/pipeline';
import type { PipelineStage, PipelineStatus } from '@/types/pipeline';

interface Props {
  stage:  PipelineStage | null;
  status: PipelineStatus;
}

const STAGE_ORDER: PipelineStage[] = ['vad', 'stt', 'emotion', 'tts'];

function idx(s: PipelineStage | null) {
  return s ? STAGE_ORDER.indexOf(s) : -1;
}

export default function PipelineStatus({ stage, status }: Props) {
  const cur  = idx(stage);
  const done = status === 'playing' || status === 'idle';

  return (
    <div className="flex items-center gap-1.5 justify-center">
      {PIPELINE_STAGES.map(({ key, label }, i) => {
        const isDone   = done || cur > i;
        const isActive = cur === i;

        return (
          <div key={key} className="flex items-center gap-1.5">
            <motion.div
              animate={{
                background: isDone    ? '#c084fc18'
                           : isActive ? '#c084fc0e'
                           :            'rgba(0,0,0,0.04)',
                borderColor: isDone    ? '#c084fc55'
                            : isActive ? '#c084fc44'
                            :            'rgba(0,0,0,0.10)',
              }}
              transition={{ duration: 0.25 }}
              className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] border font-medium"
            >
              {isActive && (
                <motion.span
                  animate={{ scale: [1, 1.3, 1] }}
                  transition={{ duration: 0.9, repeat: Infinity }}
                  className="w-1 h-1 rounded-full bg-purple-400 shrink-0"
                />
              )}
              {isDone && (
                <span className="w-1 h-1 rounded-full bg-purple-400 shrink-0" />
              )}
              <span style={{ color: isDone || isActive ? '#9333ea' : 'var(--muted)' }}>
                {label}
              </span>
            </motion.div>

            {i < PIPELINE_STAGES.length - 1 && (
              <motion.span
                animate={{ opacity: cur > i ? 0.7 : 0.2 }}
                className="text-[10px] text-muted select-none"
              >
                →
              </motion.span>
            )}
          </div>
        );
      })}
    </div>
  );
}
