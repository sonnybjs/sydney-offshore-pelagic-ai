/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      borderRadius: {
        panel: '8px',
        btn: '7px',
      },
      boxShadow: {
        panel: 'var(--shadow-panel)',
        overlay: 'var(--shadow-overlay)',
        pin: 'var(--shadow-pin)',
      },
    },
  },
  plugins: [],
};
