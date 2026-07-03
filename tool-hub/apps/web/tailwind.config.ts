import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "../../modules/*/frontend/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0A0C10",
        panel: "#12151C",
        "panel-raised": "#171B24",
        border: "#232833",
        "border-bright": "#343B4A",
        "text-primary": "#E9EBF0",
        "text-secondary": "#8A91A3",
        "text-dim": "#545B6B",
        "accent-a": "#FF8A34",
        "accent-b": "#6E86FF",
        ok: "#3ED598",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
