'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Square, RotateCcw } from 'lucide-react';
import type { PipelineStatus } from '@/types/pipeline';

interface Props {
  status:       PipelineStatus;
  accentColor:  string;
  onStart:      () => void;
  onStop:       () => void;
  onReset:      () => void;
  onFileChange: (file: File) => void;
}

const STATUS_LABEL: Record<PipelineStatus, string> = {
  idle:       '말하기',
  recording:  '클릭해서 중지',
  processing: '처리 중…',
  playing:    '처음으로 돌아가기',
  error:      '다시 시도',
};

export default function VoiceButton({
  status, accentColor, onStart, onStop, onReset, onFileChange,
}: Props) {
  const isRecording  = status === 'recording';
  const isProcessing = status === 'processing';
  const isDone       = status === 'playing' || status === 'error';

  const handleClick = () => {
    if (isRecording)   return onStop();
    if (isDone)        return onReset();
    if (!isProcessing) return onStart();
  };

  return (
    <div className="flex flex-col items-center gap-5">
      {/* Button */}
      <div className="relative flex items-center justify-center">
        {/* Pulse rings */}
        {isRecording && (
          <>
            <span className="absolute rounded-full animate-pulse-ring pointer-events-none"
                  style={{ width: 128, height: 128, border: `1.5px solid ${accentColor}`, opacity: 0.5 }} />
            <span className="absolute rounded-full animate-pulse-ring2 pointer-events-none"
                  style={{ width: 160, height: 160, border: `1.5px solid ${accentColor}`, opacity: 0.25 }} />
          </>
        )}

        <motion.button
          onClick={handleClick}
          disabled={isProcessing}
          whileTap={{ scale: 0.90 }}
          whileHover={{ scale: isProcessing ? 1 : 1.04 }}
          animate={{
            background: isRecording  ? '#ef4444'
                       : isProcessing ? 'rgba(0,0,0,0.05)'
                       : accentColor,
            boxShadow: isRecording
              ? '0 0 40px rgba(239,68,68,0.5), 0 0 80px rgba(239,68,68,0.15)'
              : isProcessing
              ? 'none'
              : `0 0 32px ${accentColor}55, 0 0 64px ${accentColor}22`,
          }}
          transition={{ duration: 0.35 }}
          className="relative z-10 w-[88px] h-[88px] rounded-full flex items-center justify-center
                     cursor-pointer disabled:cursor-wait"
        >
          <AnimatePresence mode="wait">
            {isRecording ? (
              <motion.div key="stop"
                initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }}
                exit={{ scale: 0 }} transition={{ duration: 0.18 }}>
                <Square size={26} className="text-white fill-white/90" />
              </motion.div>
            ) : isProcessing ? (
              <motion.div key="proc"
                animate={{ rotate: 360 }} transition={{ duration: 1.1, repeat: Infinity, ease: 'linear' }}>
                <div className="w-7 h-7 rounded-full border-2 border-transparent"
                     style={{ borderTopColor: accentColor }} />
              </motion.div>
            ) : isDone ? (
              <motion.div key="reset"
                initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                <RotateCcw size={24} className="text-white" />
              </motion.div>
            ) : (
              <motion.div key="mic"
                initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                <Mic size={28} className="text-white" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
      </div>

      {/* Label */}
      <motion.p
        key={status}
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-sm font-medium text-sub select-none"
      >
        {STATUS_LABEL[status]}
      </motion.p>

      {/* File upload */}
      <AnimatePresence>
        {!isRecording && !isProcessing && (
          <motion.label
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-medium
                       text-muted cursor-pointer transition-all"
            style={{ border: '1px solid rgba(0,0,0,0.10)' }}
          >
            오디오 파일 업로드
            <input
              type="file" accept="audio/*" className="hidden"
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) { onFileChange(f); e.target.value = ''; }
              }}
            />
          </motion.label>
        )}
      </AnimatePresence>
    </div>
  );
}
