'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useVoicePipeline } from '@/hooks/useVoicePipeline';
import { EMOTION_CONFIG }   from '@/types/pipeline';
import type { EmotionResult, EmotionLabel, PipelineMetrics } from '@/types/pipeline';
import VoiceButton          from '@/components/VoiceButton';
import WaveformVisualizer   from '@/components/WaveformVisualizer';
import PipelineStatus       from '@/components/PipelineStatus';
import EmotionCard          from '@/components/EmotionCard';
import AudioPlayer          from '@/components/AudioPlayer';
import MetricsPanel         from '@/components/MetricsPanel';

const API = process.env.NEXT_PUBLIC_API_URL ?? '';

interface VoiceOption { name: string; lang: string; }

interface Turn {
  id:        number;
  user:      string;
  ai:        string;
  emotion:   EmotionResult | null;
}

// ── Chat bubble components ─────────────────────────────────────────────────
function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%]">
        <div className="px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed font-medium"
             style={{ background: '#18181b', color: '#fafafa' }}>
          {text}
        </div>
        <p className="text-[10px] mt-1 text-right pr-1" style={{ color: 'var(--muted)' }}>나</p>
      </div>
    </div>
  );
}

function AIBubble({ text, emotion, name }: { text: string; emotion: EmotionResult | null; name: string }) {
  const label  = emotion?.emotion_label ?? 'neutral';
  const cfg    = EMOTION_CONFIG[label];
  return (
    <div className="flex justify-start">
      <div className="max-w-[78%]">
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed"
             style={{
               background:  '#ffffff',
               color:       '#09090b',
               border:      '1px solid rgba(0,0,0,0.07)',
               borderLeft:  `3px solid ${cfg.primary}`,
               boxShadow:   '0 1px 4px rgba(0,0,0,0.06)',
             }}>
          {text}
        </div>
        <p className="text-[10px] mt-1 pl-1 font-medium" style={{ color: cfg.primary }}>
          {cfg.emoji} {name} {emotion ? `(${cfg.label})` : ''}
        </p>
      </div>
    </div>
  );
}

export default function Home() {
  const [voice, setVoice]         = useState('Yuna');
  const [voices, setVoices]       = useState<VoiceOption[]>([]);
  const [showVoices, setShowVoices] = useState(false);
  const [turns, setTurns]         = useState<Turn[]>([]);
  // Persist last emotion/metrics so analysis doesn't vanish between turns
  const [lastEmotion, setLastEmotion] = useState<EmotionResult | null>(null);
  const [lastMetrics, setLastMetrics] = useState<PipelineMetrics | null>(null);
  const bottomRef                  = useRef<HTMLDivElement>(null);

  const { state, micStream, startRecording, stopRecording, processFile, reset, continueConversation } =
    useVoicePipeline(voice, 'ko');

  // After 1st turn completes, keep showing last emotion/metrics while idle
  const displayEmotion = state.emotion ?? (turns.length > 0 ? lastEmotion : null);
  const displayMetrics = state.metrics ?? (turns.length > 0 ? lastMetrics : null);

  const emotion = displayEmotion?.emotion_label ?? 'neutral';
  const cfg     = EMOTION_CONFIG[emotion];
  const accent  = cfg.primary;

  // Auto-scroll conversation to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, state.transcript, state.aiResponse]);

  // Fetch voices
  useEffect(() => {
    fetch(`${API}/api/voices`)
      .then(r => r.json())
      .then(d => { if (d.voices) setVoices(d.voices); if (d.default) setVoice(d.default); })
      .catch(() => {});
  }, []);

  // When audio finishes playing → save turn + soft reset to idle
  const handlePlayEnd = useCallback(() => {
    if (state.transcript || state.aiResponse) {
      setTurns(prev => [...prev, {
        id:      Date.now(),
        user:    state.transcript,
        ai:      state.aiResponse,
        emotion: state.emotion,
      }]);
    }
    // Persist analysis so it stays visible during next turn
    if (state.emotion)  setLastEmotion(state.emotion);
    if (state.metrics)  setLastMetrics(state.metrics);
    continueConversation();
  }, [state, continueConversation]);

  // Full conversation reset
  const handleFullReset = useCallback(() => {
    setTurns([]);
    setLastEmotion(null);
    setLastMetrics(null);
    reset();
  }, [reset]);

  const isRecording  = state.status === 'recording';
  const isProcessing = state.status === 'processing';
  const hasCurrentTurn = !!(state.transcript || state.aiResponse);
  const hasAnyContent  = turns.length > 0 || hasCurrentTurn;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>

      {/* ── Subtle emotion tint at top ─────────────────────────────────────── */}
      <div className="pointer-events-none fixed top-0 left-0 right-0 h-64 z-0 overflow-hidden">
        <motion.div
          animate={{
            background: `radial-gradient(ellipse 100% 100% at 50% -20%, ${cfg.primary}18, transparent 70%)`,
          }}
          transition={{ duration: 1.5, ease: 'easeInOut' }}
          className="absolute inset-0"
        />
      </div>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="relative z-30 flex items-center justify-between px-5 py-4 sticky top-0"
              style={{ background: 'rgba(242,242,247,0.85)', backdropFilter: 'blur(12px)',
                       borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
        <div className="flex items-center gap-2.5">
          <motion.div
            animate={{ boxShadow: `0 0 14px ${accent}44` }}
            transition={{ duration: 1 }}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-sm"
            style={{ background: `${accent}18`, border: `1px solid ${accent}30` }}
          >
            🎙
          </motion.div>
          <span className="text-sm font-bold tracking-tight text-zinc-800">Emotion Aware AI Voice Engine</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Voice selector */}
          <div className="relative">
            <button
              onClick={() => setShowVoices(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                         text-zinc-500 transition-colors hover:bg-black/[0.05]"
              style={{ background: 'rgba(0,0,0,0.04)', border: '1px solid rgba(0,0,0,0.07)' }}
            >
              {voice}
              <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                <path d="M1.5 3l2.5 2.5L6.5 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              </svg>
            </button>
            <AnimatePresence>
              {showVoices && voices.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: -6, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-2 w-48 rounded-2xl z-50 shadow-xl overflow-hidden"
                  style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)' }}
                >
                  <div className="p-1.5 max-h-60 overflow-y-auto">
                    {voices.map(v => (
                      <button key={v.name}
                        onClick={() => { setVoice(v.name); setShowVoices(false); }}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs
                                   hover:bg-zinc-50 transition-colors text-left"
                      >
                        <span className={voice === v.name ? 'text-zinc-900 font-semibold' : 'text-zinc-500'}>
                          {v.name}
                        </span>
                        <span className="text-zinc-400 text-[10px]">{v.lang}</span>
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Status */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium"
               style={{ background: 'rgba(0,0,0,0.04)', border: '1px solid rgba(0,0,0,0.06)' }}>
            <motion.span
              animate={{
                backgroundColor:
                  state.status === 'recording'  ? '#ef4444' :
                  state.status === 'processing' ? '#f59e0b' :
                  state.status === 'playing'    ? '#22c55e' :
                  state.status === 'error'      ? '#ef4444' : '#d4d4d8',
                boxShadow: state.status === 'recording' ? '0 0 8px #ef444466' : 'none',
              }}
              className="w-1.5 h-1.5 rounded-full"
            />
            <span className="text-zinc-500">
              {state.status === 'idle'       ? '대기'    :
               state.status === 'recording'  ? '녹음 중' :
               state.status === 'processing' ? '처리 중' :
               state.status === 'playing'    ? '재생 중' : '오류'}
            </span>
          </div>

          {/* Reset button (only shows when conversation started) */}
          {hasAnyContent && (
            <button
              onClick={handleFullReset}
              className="px-3 py-1.5 rounded-full text-[11px] font-medium text-zinc-400
                         hover:text-zinc-600 hover:bg-black/[0.05] transition-colors"
            >
              초기화
            </button>
          )}
        </div>
      </header>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main className="relative z-10 flex-1 flex flex-col items-center px-4 pb-10">
        <div className="w-full max-w-[560px] flex flex-col gap-5 pt-6">

          {/* ── 1. CONVERSATION (상단) ──────────────────────────────────── */}
          <AnimatePresence>
            {hasAnyContent && (
              <motion.section
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col gap-3"
              >
                {/* Past completed turns */}
                {turns.map(turn => (
                  <div key={turn.id} className="flex flex-col gap-2">
                    {turn.user && <UserBubble text={turn.user} />}
                    {turn.ai   && <AIBubble  text={turn.ai}   emotion={turn.emotion} name={voice} />}
                  </div>
                ))}

                {/* Current in-progress turn */}
                {state.transcript && (
                  <motion.div
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <UserBubble text={state.transcript} />
                  </motion.div>
                )}
                {state.aiResponse && (
                  <motion.div
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <AIBubble text={state.aiResponse} emotion={state.emotion} name={voice} />
                  </motion.div>
                )}

                <div ref={bottomRef} />
              </motion.section>
            )}
          </AnimatePresence>

          {/* ── 2. RECORDING (중단) ────────────────────────────────────── */}
          <section className="flex flex-col items-center gap-5 py-8">
            <WaveformVisualizer stream={micStream} isActive={isRecording} color={accent} />

            {/* VAD bar */}
            <AnimatePresence>
              {isRecording && (
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="w-full max-w-xs flex items-center gap-2"
                >
                  <span className="text-[10px] w-8 text-zinc-400">VAD</span>
                  <div className="flex-1 h-[3px] rounded-full overflow-hidden"
                       style={{ background: 'rgba(0,0,0,0.08)' }}>
                    <motion.div
                      className="h-full rounded-full"
                      animate={{ width: `${state.vadConfidence * 100}%` }}
                      transition={{ duration: 0.08 }}
                      style={{ background: accent }}
                    />
                  </div>
                  <span className="text-[10px] w-7 text-right text-zinc-400">
                    {Math.round(state.vadConfidence * 100)}%
                  </span>
                </motion.div>
              )}
            </AnimatePresence>

            <VoiceButton
              status={state.status}
              accentColor={accent}
              onStart={startRecording}
              onStop={stopRecording}
              onReset={handleFullReset}
              onFileChange={processFile}
            />

            <AnimatePresence>
              {isProcessing && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <PipelineStatus stage={state.stage} status={state.status} />
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {state.error && (
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="px-4 py-2.5 rounded-xl text-sm text-red-600"
                  style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
                >
                  {state.error}
                </motion.div>
              )}
            </AnimatePresence>
          </section>

          {/* ── 3. ANALYSIS (하단) ────────────────────────────────────── */}
          <section className="flex flex-col gap-3">

            {/* Audio player */}
            <AnimatePresence>
              {state.audioUrl && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <AudioPlayer
                    audioUrl={state.audioUrl}
                    accentColor={accent}
                    emotion={emotion}
                    onEnded={handlePlayEnd}
                  />
                </motion.div>
              )}
            </AnimatePresence>

            {/* Emotion analysis — persists after 1st turn */}
            <AnimatePresence>
              {displayEmotion && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.05 }}
                >
                  <EmotionCard emotion={displayEmotion} />
                </motion.div>
              )}
            </AnimatePresence>

            {/* Metrics — persists after 1st turn */}
            <AnimatePresence>
              {displayMetrics && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.1 }}
                >
                  <MetricsPanel metrics={displayMetrics} accentColor={accent} />
                </motion.div>
              )}
            </AnimatePresence>
          </section>

        </div>
      </main>

      <footer className="relative z-10 text-center pb-5 text-[10px]" style={{ color: 'var(--muted)' }}>
        VAD · Whisper STT · Prosody Fusion · Emotion TTS
      </footer>
    </div>
  );
}
