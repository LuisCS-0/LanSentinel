/** @type {import('tailwindcss').Config} */

// Los colores son variables CSS (src/index.css) para cambiar entre el tema
// oscuro y el claro sin tocar los componentes
const token = name => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter Variable'", "Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono Variable'", "ui-monospace", "monospace"],
      },
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        background: token("background"),
        foreground: token("foreground"),
        surface: token("surface"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        destructive: { DEFAULT: token("destructive"), foreground: token("destructive-foreground") },
        success: token("success"),
        warning: token("warning"),
        info: token("info"),
        upload: token("upload"),
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--primary) / 0.25), 0 8px 30px -8px hsl(var(--primary) / 0.45)",
        card: "0 1px 2px hsl(var(--shadow) / 0.08), 0 8px 24px -12px hsl(var(--shadow) / 0.25)",
      },
      keyframes: {
        "fade-in": { from: { opacity: 0 }, to: { opacity: 1 } },
        "slide-in-right": { from: { transform: "translateX(100%)" }, to: { transform: "translateX(0)" } },
        "slide-in-left": { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(0)" } },
        "zoom-in": { from: { opacity: 0, transform: "scale(0.96)" }, to: { opacity: 1, transform: "scale(1)" } },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 hsl(var(--success) / 0.6)" },
          "100%": { boxShadow: "0 0 0 6px hsl(var(--success) / 0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "slide-in-right": "slide-in-right 220ms cubic-bezier(0.32, 0.72, 0, 1)",
        "slide-in-left": "slide-in-left 220ms cubic-bezier(0.32, 0.72, 0, 1)",
        "zoom-in": "zoom-in 160ms ease-out",
        "pulse-ring": "pulse-ring 1.6s ease-out infinite",
      },
    },
  },
  plugins: [],
}
