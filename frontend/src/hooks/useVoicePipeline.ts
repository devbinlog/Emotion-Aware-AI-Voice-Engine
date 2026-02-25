'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import type {
  PipelineState, PipelineStage, EmotionResult, PipelineMetrics,
} from '@/types/pipeline';

const API = process.env.NEXT_PUBLIC_API_URL ?? '';
const WS  = (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000') + '/ws/voice';

const INITIAL: PipelineState = {
  status:        'idle',
  stage:         null,
  transcript:    '',
  aiResponse:    '',
  emotion:       null,
  metrics:       null,
  audioUrl:      null,
  vadConfidence: 0,
  error:         null,
};

// ── helpers ──────────────────────────────────────────────────────────────────
function float32ToBase64(f: Float32Array): string {
  const bytes = new Uint8Array(f.buffer);
  let bin = '';
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function base64ToUint8(b64: string): Uint8Array {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

// ── hook ─────────────────────────────────────────────────────────────────────
export function useVoicePipeline(voice = 'Yuna', language = 'ko') {
  const [state, setState] = useState<PipelineState>(INITIAL);

  // WebSocket / recording refs
  const wsRef       = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const wavChunks   = useRef<Uint8Array[]>([]);
  const prevUrl     = useRef<string | null>(null);

  // ── KEY FIX: accumulate all MediaRecorder blobs, decode after stop ──────
  const blobChunks = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string>('audio/webm');

  // Conversation history (persists across turns for multi-turn LLM)
  const historyRef   = useRef<{ role: string; content: string }[]>([]);
  const pendingTr    = useRef('');   // current turn transcript
  const pendingAi    = useRef('');   // current turn AI response

  const patch = useCallback((p: Partial<PipelineState>) =>
    setState(prev => ({ ...prev, ...p })), []);

  // ── Message handler ────────────────────────────────────────────────────────
  const onMessage = useCallback((raw: string) => {
    const msg = JSON.parse(raw);
    switch (msg.type) {
      case 'vad_event':
        patch({ vadConfidence: msg.confidence });
        break;

      case 'final_transcript':
        pendingTr.current = msg.text ?? '';
        patch({ transcript: msg.text ?? '', stage: 'emotion' });
        break;

      case 'ai_response':
        pendingAi.current = msg.text ?? '';
        patch({ aiResponse: msg.text ?? '' });
        break;

      case 'emotion':
        patch({
          emotion: {
            emotion_label:    msg.emotion_label,
            intensity:        msg.intensity,
            probabilities:    msg.probabilities,
            features_summary: msg.features_summary,
          } as EmotionResult,
          stage: 'tts',
        });
        break;

      case 'audio_chunk':
        wavChunks.current.push(base64ToUint8(msg.data));
        if (msg.is_last) {
          // Save this turn to history for next turn's LLM context
          historyRef.current = [
            ...historyRef.current.slice(-18),
            { role: 'user',      content: pendingTr.current || '(무음)' },
            { role: 'assistant', content: pendingAi.current },
          ];
          pendingTr.current = '';
          pendingAi.current = '';

          const blob = new Blob(wavChunks.current as BlobPart[], { type: 'audio/wav' });
          if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
          const url = URL.createObjectURL(blob);
          prevUrl.current = url;
          wavChunks.current = [];
          patch({ audioUrl: url, status: 'playing', stage: null });
          wsRef.current?.close();
        }
        break;

      case 'metrics':
        patch({
          metrics: {
            vad_ms:     msg.vad_ms,
            stt_ms:     msg.stt_ms,
            emotion_ms: msg.emotion_ms,
            tts_ms:     msg.tts_ms,
            total_ms:   msg.total_ms,
            rtf:        msg.rtf,
          } as PipelineMetrics,
        });
        break;

      case 'error':
        patch({ status: 'error', error: msg.message, stage: null });
        break;
    }
  }, [patch]);

  // ── Start recording — collect all blobs ─────────────────────────────────
  const startRecording = useCallback(async () => {
    blobChunks.current = [];
    wavChunks.current  = [];
    patch({ ...INITIAL, status: 'recording' });

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      patch({ status: 'error', error: '마이크 권한이 필요합니다.' });
      return;
    }
    streamRef.current = stream;

    const ws = new WebSocket(WS);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send config WITH conversation history (enables multi-turn LLM)
      ws.send(JSON.stringify({
        type:     'config',
        language,
        voice,
        history:  historyRef.current,   // ← server restores LLM context
      }));

      const mt = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      mimeTypeRef.current = mt;

      const recorder = new MediaRecorder(stream, { mimeType: mt });
      recorderRef.current = recorder;

      // ── Collect blobs — do NOT decode per-chunk (unreliable for WebM)
      recorder.ondataavailable = ({ data }) => {
        if (data.size > 0) blobChunks.current.push(data);
      };

      recorder.start(500);
    };

    ws.onmessage = ({ data }) => onMessage(data);
    ws.onerror   = ()         => patch({ status: 'error', error: 'WebSocket 오류' });
  }, [onMessage, patch, voice, language]);

  // ── Stop recording — onstop fires after ALL ondataavailable events ───────
  const stopRecording = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    patch({ status: 'processing', stage: 'vad' });

    const recorder = recorderRef.current;
    if (!recorder) return;

    // onstop is guaranteed to fire after the last ondataavailable
    recorder.onstop = async () => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      if (blobChunks.current.length === 0) {
        patch({ status: 'error', error: '오디오가 없습니다. 마이크를 확인하세요.' });
        return;
      }

      try {
        // Combine ALL blobs → one complete WebM file → decode reliably
        const combined = new Blob(blobChunks.current, { type: mimeTypeRef.current });
        const ab  = await combined.arrayBuffer();
        const ctx = new AudioContext({ sampleRate: 16000 });
        const dec = await ctx.decodeAudioData(ab);
        const pcm = dec.getChannelData(0);
        ctx.close();

        ws.send(JSON.stringify({
          type:        'audio_chunk',
          data:        float32ToBase64(pcm),
          sample_rate: 16000,
        }));
      } catch (e) {
        patch({ status: 'error', error: '오디오 처리 실패: ' + (e as Error).message });
        ws.close();
        return;
      }

      // end_stream sent AFTER audio chunk — no race condition
      ws.send(JSON.stringify({ type: 'end_stream', sample_rate: 16000 }));
    };

    recorder.stop();
  }, [patch]);

  // ── Soft reset — return to idle, keep conversation history ───────────────
  const continueConversation = useCallback(() => {
    if (prevUrl.current) { URL.revokeObjectURL(prevUrl.current); prevUrl.current = null; }
    wsRef.current?.close();
    patch({
      status: 'idle', stage: null,
      transcript: '', aiResponse: '',
      emotion: null, audioUrl: null,
      metrics: null, vadConfidence: 0, error: null,
    });
  }, [patch]);

  // ── Full reset — clears everything including history ─────────────────────
  const reset = useCallback(() => {
    historyRef.current = [];
    pendingTr.current  = '';
    pendingAi.current  = '';
    wsRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());
    wavChunks.current  = [];
    blobChunks.current = [];
    if (prevUrl.current) { URL.revokeObjectURL(prevUrl.current); prevUrl.current = null; }
    setState(INITIAL);
  }, []);

  // ── File upload (REST) ────────────────────────────────────────────────────
  const processFile = useCallback(async (file: File) => {
    wavChunks.current  = [];
    blobChunks.current = [];
    patch({ ...INITIAL, status: 'processing', stage: 'stt' });

    try {
      const fd1 = new FormData();
      fd1.append('file', file);
      fd1.append('language', 'ko');
      const sttRes = await fetch(`${API}/api/transcribe`, { method: 'POST', body: fd1 });
      if (!sttRes.ok) throw new Error('STT 실패');
      const stt = await sttRes.json();
      pendingTr.current = stt.transcript ?? '';
      patch({ transcript: stt.transcript, stage: 'emotion' });

      const fd2 = new FormData();
      fd2.append('file', file);
      fd2.append('transcript', stt.transcript ?? '');
      const emoRes = await fetch(`${API}/api/analyze-emotion`, { method: 'POST', body: fd2 });
      if (!emoRes.ok) throw new Error('감정 분석 실패');
      const emo = await emoRes.json();
      patch({ emotion: emo as EmotionResult, stage: 'tts' });

      const ttsRes = await fetch(`${API}/api/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text:          stt.transcript || '네, 말씀하셨군요.',
          emotion_label: emo.emotion_label,
          intensity:     emo.intensity,
          language:      'ko',
        }),
      });
      if (!ttsRes.ok) throw new Error('TTS 실패');
      const blob = await ttsRes.blob();
      if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
      const url = URL.createObjectURL(blob);
      prevUrl.current = url;

      // Save to history
      const aiText = emo.emotion_label + ' 응답';
      historyRef.current = [
        ...historyRef.current.slice(-18),
        { role: 'user',      content: stt.transcript || '(파일)' },
        { role: 'assistant', content: aiText },
      ];

      patch({
        audioUrl: url,
        status:   'playing',
        stage:    null,
        metrics: {
          vad_ms:     0,
          stt_ms:     Math.round(stt.latency_ms ?? 0),
          emotion_ms: Math.round(emo.latency_ms ?? 0),
          tts_ms:     Math.round(parseFloat(ttsRes.headers.get('X-Latency-Ms') ?? '0')),
          total_ms:   Math.round((stt.latency_ms ?? 0) + (emo.latency_ms ?? 0) +
                        parseFloat(ttsRes.headers.get('X-Latency-Ms') ?? '0')),
        },
      });
    } catch (e) {
      patch({ status: 'error', error: (e as Error).message, stage: null });
    }
  }, [patch]);

  // ── Cleanup ───────────────────────────────────────────────────────────────
  useEffect(() => () => {
    wsRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());
    if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
  }, []);

  return { state, startRecording, stopRecording, processFile, reset, continueConversation };
}
