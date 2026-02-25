'use client';

import { useRef, useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Play, Pause } from 'lucide-react';
import { EMOTION_CONFIG } from '@/types/pipeline';
import type { EmotionLabel } from '@/types/pipeline';

interface Props {
  audioUrl:    string | null;
  accentColor: string;
  emotion:     EmotionLabel;
  onEnded?:    () => void;   // ← called when playback finishes
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

export default function AudioPlayer({ audioUrl, accentColor, emotion, onEnded }: Props) {
  const audioRef  = useRef<HTMLAudioElement>(null);
  const [playing,  setPlaying]  = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [currentT, setCurrentT] = useState(0);

  useEffect(() => {
    if (!audioUrl || !audioRef.current) return;
    audioRef.current.src = audioUrl;
    audioRef.current.play().catch(() => {});
    setPlaying(true);
    setProgress(0);
    setCurrentT(0);
  }, [audioUrl]);

  const toggle = () => {
    if (!audioRef.current) return;
    if (playing) { audioRef.current.pause(); setPlaying(false); }
    else         { audioRef.current.play();  setPlaying(true);  }
  };

  const cfg = EMOTION_CONFIG[emotion];

  if (!audioUrl) return null;

  return (
    <div className="card px-5 py-4 flex items-center gap-4">
      <motion.button
        onClick={toggle}
        whileTap={{ scale: 0.88 }}
        className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
        style={{ background: accentColor, boxShadow: `0 2px 12px ${accentColor}44` }}
      >
        {playing
          ? <Pause size={15} className="text-white fill-white" />
          : <Play  size={15} className="text-white fill-white ml-0.5" />
        }
      </motion.button>

      <div className="flex-1 flex flex-col gap-1.5">
        <div className="flex items-center">
          <span className="text-xs font-medium" style={{ color: accentColor }}>
            {cfg.emoji} {cfg.label} 응답
          </span>
          <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>
            {fmt(currentT)} / {fmt(duration)}
          </span>
        </div>
        <input
          type="range" min={0} max={100} value={progress}
          onChange={e => {
            if (!audioRef.current || !duration) return;
            const t = (Number(e.target.value) / 100) * duration;
            audioRef.current.currentTime = t;
            setProgress(Number(e.target.value));
          }}
          className="w-full"
          style={{
            background: `linear-gradient(to right, ${accentColor} ${progress}%, rgba(0,0,0,0.10) ${progress}%)`,
          }}
        />
      </div>

      <audio
        ref={audioRef}
        onTimeUpdate={() => {
          if (!audioRef.current) return;
          setCurrentT(audioRef.current.currentTime);
          setProgress((audioRef.current.currentTime / audioRef.current.duration) * 100 || 0);
        }}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration ?? 0)}
        onEnded={() => {
          setPlaying(false);
          onEnded?.();   // ← triggers continueConversation in page.tsx
        }}
      />
    </div>
  );
}
