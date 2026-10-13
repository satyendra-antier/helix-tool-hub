/** Per-module professional accent palette */
export type ModuleTheme = {
  id: string;
  label: string;
  accent: string;
  accentHover: string;
  accentMuted: string;
  accentBorder: string;
  gradient: string;
  iconClass: string;
  badgeVariant: "primary" | "success" | "warning" | "default";
};

export const MODULE_THEMES: Record<string, ModuleTheme> = {
  "market-depth-analyzer": {
    id: "market-depth-analyzer",
    label: "Step 1 · Find Demand",
    accent: "#2563eb",
    accentHover: "#1d4ed8",
    accentMuted: "#eff6ff",
    accentBorder: "#bfdbfe",
    gradient: "from-blue-600 to-indigo-600",
    iconClass: "bg-blue-50 text-blue-600 border-blue-100",
    badgeVariant: "primary",
  },
  "build-readiness": {
    id: "build-readiness",
    label: "Step 2 · Check Fit",
    accent: "#0d9488",
    accentHover: "#0f766e",
    accentMuted: "#f0fdfa",
    accentBorder: "#99f6e4",
    gradient: "from-teal-500 to-cyan-600",
    iconClass: "bg-teal-50 text-teal-600 border-teal-100",
    badgeVariant: "success",
  },
  "lead-intelligence": {
    id: "lead-intelligence",
    label: "Step 3 · Find Leads",
    accent: "#7c3aed",
    accentHover: "#6d28d9",
    accentMuted: "#f5f3ff",
    accentBorder: "#ddd6fe",
    gradient: "from-violet-600 to-purple-600",
    iconClass: "bg-violet-50 text-violet-600 border-violet-100",
    badgeVariant: "primary",
  },
  "growth-pillars": {
    id: "growth-pillars",
    label: "Step 4 · Win Leads",
    accent: "#c026d3",
    accentHover: "#a21caf",
    accentMuted: "#fdf4ff",
    accentBorder: "#f5d0fe",
    gradient: "from-fuchsia-600 to-pink-600",
    iconClass: "bg-fuchsia-50 text-fuchsia-600 border-fuchsia-100",
    badgeVariant: "primary",
  },
  "outreach-autopilot": {
    id: "outreach-autopilot",
    label: "Step 5 · Reach Out",
    accent: "#e11d48",
    accentHover: "#be123c",
    accentMuted: "#fff1f2",
    accentBorder: "#fecdd3",
    gradient: "from-rose-500 to-orange-500",
    iconClass: "bg-rose-50 text-rose-600 border-rose-100",
    badgeVariant: "primary",
  },
  "video-scraper": {
    id: "video-scraper",
    label: "Proof Library",
    accent: "#d97706",
    accentHover: "#b45309",
    accentMuted: "#fffbeb",
    accentBorder: "#fde68a",
    gradient: "from-amber-500 to-orange-600",
    iconClass: "bg-amber-50 text-amber-600 border-amber-100",
    badgeVariant: "warning",
  },
};

export function getModuleTheme(moduleId: string): ModuleTheme {
  return MODULE_THEMES[moduleId] ?? MODULE_THEMES["market-depth-analyzer"];
}
