/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx}',
    './index.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['Poppins', 'sans-serif'],
        serif: ['"Source Serif 4"', 'serif'],
      },
      borderRadius: {
        DEFAULT: '1rem',
      },
    },
  },
  plugins: [],
}
