import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(215 18% 20%)",
        input: "hsl(215 18% 22%)",
        ring: "hsl(215 80% 55%)",
        background: "hsl(222 24% 9%)",
        foreground: "hsl(210 20% 94%)",
        muted: {
          DEFAULT: "hsl(215 16% 16%)",
          foreground: "hsl(215 12% 65%)",
        },
        card: {
          DEFAULT: "hsl(222 22% 12%)",
          foreground: "hsl(210 20% 94%)",
        },
        popover: {
          DEFAULT: "hsl(222 22% 12%)",
          foreground: "hsl(210 20% 94%)",
        },
        primary: {
          DEFAULT: "hsl(215 80% 55%)",
          foreground: "hsl(0 0% 100%)",
        },
        secondary: {
          DEFAULT: "hsl(215 16% 18%)",
          foreground: "hsl(210 20% 94%)",
        },
        destructive: {
          DEFAULT: "hsl(0 72% 51%)",
          foreground: "hsl(0 0% 100%)",
        },
        success: {
          DEFAULT: "hsl(150 55% 42%)",
          foreground: "hsl(0 0% 100%)",
        },
        warning: {
          DEFAULT: "hsl(35 90% 55%)",
          foreground: "hsl(222 24% 9%)",
        },
        accent: {
          DEFAULT: "hsl(215 30% 20%)",
          foreground: "hsl(210 20% 94%)",
        },
      },
      borderRadius: {
        lg: "0.6rem",
        md: "0.45rem",
        sm: "0.3rem",
      },
      fontFamily: {
        sans: [
          "Segoe UI",
          "system-ui",
          "-apple-system",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
