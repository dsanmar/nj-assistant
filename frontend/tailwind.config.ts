import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0b1220",
          700: "#1f2a44",
          500: "#3a4a6b"
        },
        slate: {
          50: "#f5f7fb",
          100: "#e7edf6",
          200: "#cdd9ea"
        },
        brand: {
          50: "#eef6ff",
          100: "#d8e8ff",
          500: "#2c6ecb",
          700: "#1e4c96"
        },
        accent: {
          500: "#f0b429",
          600: "#d99a20"
        }
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "sans-serif"]
      },
      boxShadow: {
        "soft-xl": "0 24px 60px -40px rgba(12, 24, 44, 0.4)",
        "soft-md": "0 16px 40px -28px rgba(12, 24, 44, 0.35)"
      }
    }
  },
  plugins: []
};

export default config;
