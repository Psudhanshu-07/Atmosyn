/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sky: {
          50: "#effcf8",
          100: "#d7f7ed",
          200: "#b1eddb",
          300: "#7bdec4",
          400: "#3dc9a8",
          500: "#16ae8e",
          600: "#0b8e75",
          700: "#0a725f",
          800: "#0a5c4e",
          900: "#094b41",
          950: "#042f2a",
        },
        // Risk palette (UIUX §29) — text labels always accompany colour
        "risk-verylow": "#16a34a",
        "risk-low": "#84cc16",
        "risk-moderate": "#f59e0b",
        "risk-high": "#f97316",
        "risk-veryhigh": "#dc2626",
        "risk-na": "#6b7280",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
