/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'gothic': ['Cinzel', 'serif'],
        'grim': ['Orbitron', 'monospace']
      },
      colors: {
        'gothic': {
          'darker': '#0a0a0a',
          'dark': '#2a3d52',
          'medium': '#3d4a63',
          'light': '#5a6b82'
        },
        'brass': {
          'dark': '#8b6914',
          DEFAULT: '#b08d57',
          'light': '#d4af37'
        },
        'gold': {
          DEFAULT: '#ffd700',
          'muted': '#b8960c'
        },
        'surface': {
          '1': '#111111',
          '2': '#1a1a1a',
          '3': '#222222',
          '4': '#2a2a2a'
        }
      },
      boxShadow: {
        'glow-sm': '0 0 10px rgba(124, 157, 214, 0.3)',
        'glow-md': '0 0 20px rgba(124, 157, 214, 0.5)',
        'glow-lg': '0 0 30px rgba(124, 157, 214, 0.7)',
        'glow-red': '0 0 20px rgba(220, 38, 38, 0.5)',
        'glow-purple': '0 0 20px rgba(168, 85, 247, 0.5)',
        'glow-blue': '0 0 20px rgba(96, 165, 250, 0.5)',
        'glow-cyan': '0 0 20px rgba(34, 211, 238, 0.4)',
        'glow-amber': '0 0 20px rgba(245, 158, 11, 0.35)',
        'glow-green': '0 0 20px rgba(132, 204, 22, 0.4)',
      },
    },
  },
  plugins: [],
}
