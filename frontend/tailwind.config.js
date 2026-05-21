/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50:  'hsl(var(--brand-50) / <alpha-value>)',
          100: 'hsl(var(--brand-100) / <alpha-value>)',
          200: 'hsl(var(--brand-200) / <alpha-value>)',
          300: 'hsl(var(--brand-300) / <alpha-value>)',
          400: 'hsl(var(--brand-400) / <alpha-value>)',
          500: 'hsl(var(--brand-500) / <alpha-value>)',
          600: 'hsl(var(--brand-600) / <alpha-value>)',
          700: 'hsl(var(--brand-700) / <alpha-value>)',
          800: 'hsl(var(--brand-800) / <alpha-value>)',
          900: 'hsl(var(--brand-900) / <alpha-value>)'
        },
        ink: {
          50:  'hsl(var(--ink-50) / <alpha-value>)',
          100: 'hsl(var(--ink-100) / <alpha-value>)',
          200: 'hsl(var(--ink-200) / <alpha-value>)',
          300: 'hsl(var(--ink-300) / <alpha-value>)',
          400: 'hsl(var(--ink-400) / <alpha-value>)',
          500: 'hsl(var(--ink-500) / <alpha-value>)',
          600: 'hsl(var(--ink-600) / <alpha-value>)',
          700: 'hsl(var(--ink-700) / <alpha-value>)',
          800: 'hsl(var(--ink-800) / <alpha-value>)',
          900: 'hsl(var(--ink-900) / <alpha-value>)'
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        display: ['Cormorant Garamond', 'Georgia', 'serif']
      }
    }
  },
  plugins: []
};
