/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Dark mode colors
        'dark-bg': '#000435',
        'dark-text': '#FFFFFF',
        'dark-text-secondary': '#B3B3FF',
        'dark-button': '#2D2DFF',
        'dark-button-hover': '#1C1CCC',
        
        // Light mode colors
        'light-bg': '#F9FAFB',
        'light-text': '#111827',
        'light-button': '#4F46E5',
        'light-button-hover': '#4338CA',
        
        // Status colors
        'status-gray': '#888',
        'status-blue': '#3B82F6',
        'status-green': '#10B981',
        'status-red': '#EF4444',
      },
      animation: {
        'gradient': 'gradient 15s ease infinite',
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        gradient: {
          '0%, 100%': {
            'background-size': '200% 200%',
            'background-position': 'left center'
          },
          '50%': {
            'background-size': '200% 200%',
            'background-position': 'right center'
          },
        },
        float: {
          '0%, 100%': {
            transform: 'translateY(0px)',
          },
          '50%': {
            transform: 'translateY(-20px)',
          },
        },
      },
      fontFamily: {
        'sans': ['Inter', 'Open Sans', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} 