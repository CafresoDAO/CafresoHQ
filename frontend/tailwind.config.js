/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Cafreso ecosystem palette — keep aligned with combined-dapp tokens
        brand: {
          50:  'hsl(28 100% 96%)',
          100: 'hsl(28 95% 90%)',
          200: 'hsl(28 90% 80%)',
          300: 'hsl(28 85% 70%)',
          400: 'hsl(28 80% 58%)',
          500: 'hsl(28 78% 48%)',  // primary CafresoAI orange
          600: 'hsl(22 80% 42%)',
          700: 'hsl(18 80% 36%)',
          800: 'hsl(16 75% 28%)',
          900: 'hsl(14 70% 20%)'
        },
        ink: {
          50:  'hsl(220 15% 97%)',
          100: 'hsl(220 14% 92%)',
          200: 'hsl(220 13% 82%)',
          400: 'hsl(220 10% 50%)',
          600: 'hsl(220 14% 28%)',
          800: 'hsl(220 18% 14%)',
          900: 'hsl(220 22% 8%)'
        }
      },
      fontFamily: {
        sans:  ['Inter', 'system-ui', 'sans-serif'],
        mono:  ['JetBrains Mono', 'ui-monospace', 'monospace']
      }
    }
  },
  plugins: []
};
