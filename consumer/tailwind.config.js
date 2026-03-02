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
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { 'box-shadow': '0 0 10px currentColor' },
          '50%': { 'box-shadow': '0 0 25px currentColor' }
        },
        'fade-in-down': {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' }
        },
        'scan-line': {
          '0%': { top: '0%' },
          '100%': { top: '100%' }
        }
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'fade-in-down': 'fade-in-down 0.5s ease-out',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'scan-line': 'scan-line 2s ease-in-out infinite'
      }
    },
  },
  plugins: [],
}
