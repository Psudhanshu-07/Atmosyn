/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
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
