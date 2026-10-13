import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
