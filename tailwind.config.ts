import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--color-paper)',
        surface: 'var(--color-surface)',
        ink: {
          DEFAULT: 'var(--color-ink)',
          2: 'var(--color-ink-2)',
          3: 'var(--color-ink-3)',
        },
        line: {
          DEFAULT: 'var(--color-line)',
          strong: 'var(--color-line-strong)',
        },
        brand: {
          DEFAULT: 'var(--color-brand)',
          wash: 'var(--color-brand-wash)',
        },
        turmeric: {
          DEFAULT: 'var(--color-turmeric)',
          wash: 'var(--color-turmeric-wash)',
        },
        madder: {
          DEFAULT: 'var(--color-madder)',
          wash: 'var(--color-madder-wash)',
        },
        ok: 'var(--color-ok)',
      },
      borderRadius: {
        chip: 'var(--radius-chip)',
        control: 'var(--radius-control)',
        overlay: 'var(--radius-overlay)',
      },
      boxShadow: {
        overlay: 'var(--shadow-overlay)',
      },
      fontFamily: {
        sans: ['var(--font-ui)'],
        serif: ['var(--font-serif)'],
      },
      maxWidth: {
        page: '1360px',
      },
      fontSize: {
        'meta': ['12px', { lineHeight: '16px' }],
        'meta-md': ['13px', { lineHeight: '18px' }],
        'body': ['14px', { lineHeight: '1.5' }],
        'body-lg': ['16px', { lineHeight: '1.5' }],
        'section': ['20px', { lineHeight: '1.25' }],
        'page-title': ['28px', { lineHeight: '1.25' }],
        'display': ['40px', { lineHeight: '1.15' }],
      },
    },
  },
  plugins: [],
} satisfies Config;
