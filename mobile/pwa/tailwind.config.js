/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        argus: {
          bg:      '#050d1a',
          surface: '#0a1628',
          card:    '#111d32',
          border:  '#1a2d4a',
          accent:  '#00c9ff',
          cyan:    '#00e5ff',
          green:   '#00e676',
          yellow:  '#ffd600',
          orange:  '#ff9100',
          red:     '#ff1744',
          text:    '#e0e7ef',
          muted:   '#8899aa',
        },
      },
      fontFamily: {
        exo2:     ['"Exo 2"', 'sans-serif'],
        rajdhani: ['Rajdhani', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
