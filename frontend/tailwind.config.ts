import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      animation: {
        'pulse-ring':  'pulseRing 1.8s cubic-bezier(0.4,0,0.6,1) infinite',
        'pulse-ring2': 'pulseRing 1.8s cubic-bezier(0.4,0,0.6,1) infinite 0.6s',
        'fade-in':     'fadeIn 0.4s ease forwards',
        'slide-up':    'slideUp 0.4s ease forwards',
        'aurora':      'aurora 12s ease infinite alternate',
      },
      keyframes: {
        pulseRing: {
          '0%,100%': { transform: 'scale(1)',    opacity: '0.6' },
          '50%':     { transform: 'scale(1.35)', opacity: '0'   },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to:   { opacity: '1', transform: 'translateY(0)'    },
        },
        aurora: {
          '0%':   { backgroundPosition: '0% 50%'   },
          '50%':  { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%'   },
        },
      },
      backdropBlur: { xs: '4px' },
      colors: {
        surface: 'rgba(255,255,255,0.04)',
      },
    },
  },
  plugins: [],
};

export default config;
