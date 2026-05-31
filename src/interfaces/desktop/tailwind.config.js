/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/renderer/**/*.{js,ts,jsx,tsx,html}'],
  theme: {
    extend: {
      colors: {
        'app-bg': '#0d1117',
        'app-sidebar': '#161b22',
        'app-panel': '#21262d',
        'app-border': '#30363d',
        'app-text': '#c9d1d9',
        'app-text-dim': '#8b949e',
        'app-accent': '#58a6ff',
        'app-accent-green': '#3fb950',
        'app-accent-red': '#f85149',
        'app-accent-yellow': '#d29922',
        'app-selection': '#388bfd26',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
