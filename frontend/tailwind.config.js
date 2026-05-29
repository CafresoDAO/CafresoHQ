/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Cafreso Pages semantic tokens (shadcn / bits-ui) ──
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        // ── CafresoAI numeric scale + Cafreso Pages named aliases, unified under `brand` ──
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
          900: 'hsl(var(--brand-900) / <alpha-value>)',
          crema: 'hsl(var(--brand-crema))',
          peach: 'hsl(var(--brand-peach))',
          coffee: 'hsl(var(--brand-coffee))',
          banana: 'hsl(var(--brand-banana))',
          'banana-rim': 'hsl(var(--brand-banana-rim))',
          'icp-gold': 'hsl(var(--brand-icp-gold))',
          leaf: 'hsl(var(--brand-leaf))',
          'farm-sky': 'hsl(var(--brand-farm-sky))',
          'cart-badge': 'hsl(var(--brand-cart-badge))',
          'link-green': 'hsl(var(--brand-link-green))',
          'link-green-hover': 'hsl(var(--brand-link-green-hover))'
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
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        // Cafreso brand display face — matches cafreso.com headings.
        display: ['Playfair Display', 'Georgia', 'serif']
      },
      fontWeight: { extrabold: '800' },
      keyframes: {
        'accordion-down': { from: { height: '0' }, to: { height: 'var(--bits-accordion-content-height)' } },
        'accordion-up': { from: { height: 'var(--bits-accordion-content-height)' }, to: { height: '0' } },
        'caret-blink': { '0%,70%,100%': { opacity: '1' }, '20%,50%': { opacity: '0' } },
        pop: {
          '0%': { transform: 'scale(0.3)', opacity: '0' },
          '70%': { transform: 'scale(1.15)' },
          '100%': { transform: 'scale(1)', opacity: '1' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'caret-blink': 'caret-blink 1.25s ease-out infinite',
        pop: 'pop 0.4s cubic-bezier(.2,.8,.2,1)'
      }
    }
  },
  plugins: []
};
