'use client';

import { useRef, useEffect } from 'react';

interface Props {
  stream:    MediaStream | null;
  isActive:  boolean;
  color?:    string;
}

export default function WaveformVisualizer({ stream, isActive, color = '#c084fc' }: Props) {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const rafRef     = useRef<number>(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const ctxAudioRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    if (!isActive || !stream) {
      // Draw idle waveform (gentle sine)
      cancelAnimationFrame(rafRef.current);
      let t = 0;
      const drawIdle = () => {
        const { width: w, height: h } = canvas;
        ctx.clearRect(0, 0, w, h);
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.lineWidth = 2;
        for (let x = 0; x < w; x++) {
          const y = h / 2 + Math.sin((x / w) * Math.PI * 4 + t) * 6;
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
        t += 0.015;
        rafRef.current = requestAnimationFrame(drawIdle);
      };
      drawIdle();
      return () => cancelAnimationFrame(rafRef.current);
    }

    // Live waveform from mic stream
    const audioCtx   = new AudioContext();
    const source      = audioCtx.createMediaStreamSource(stream);
    const analyser    = audioCtx.createAnalyser();
    analyser.fftSize  = 256;
    source.connect(analyser);
    analyserRef.current = analyser;
    ctxAudioRef.current = audioCtx;

    const data = new Uint8Array(analyser.frequencyBinCount);

    const drawLive = () => {
      analyser.getByteTimeDomainData(data);
      const { width: w, height: h } = canvas;
      ctx.clearRect(0, 0, w, h);

      // Glow line
      ctx.shadowBlur   = 12;
      ctx.shadowColor  = color;
      ctx.strokeStyle  = color;
      ctx.lineWidth    = 2.5;
      ctx.beginPath();
      data.forEach((v, i) => {
        const x = (i / data.length) * w;
        const y = ((v / 128) - 1) * (h / 2.2) + h / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.shadowBlur = 0;

      rafRef.current = requestAnimationFrame(drawLive);
    };
    drawLive();

    return () => {
      cancelAnimationFrame(rafRef.current);
      audioCtx.close();
    };
  }, [isActive, stream, color]);

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={80}
      className="w-full max-w-md"
      style={{ imageRendering: 'pixelated' }}
    />
  );
}
