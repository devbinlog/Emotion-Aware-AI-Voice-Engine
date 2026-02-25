'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { FileText } from 'lucide-react';

interface Props {
  transcript:  string;
  accentColor: string;
}

export default function TranscriptCard({ transcript, accentColor }: Props) {
  return (
    <div className="glass rounded-2xl p-5 flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <FileText size={14} style={{ color: accentColor }} />
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          트랜스크립트
        </span>
      </div>

      {/* Body */}
      <AnimatePresence mode="wait">
        {transcript ? (
          <motion.p
            key={transcript}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="text-base leading-relaxed text-slate-200 flex-1"
          >
            {transcript}
          </motion.p>
        ) : (
          <motion.p
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-slate-400 text-sm italic flex-1"
          >
            음성을 인식하면 여기에 텍스트가 표시됩니다.
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
