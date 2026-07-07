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
    label: "Market Depth",
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
    label: "Build Readiness",
    accent: "#059669",
    accentHover: "#047857",
    accentMuted: "#ecfdf5",
    accentBorder: "#a7f3d0",
    gradient: "from-emerald-600 to-teal-600",
    iconClass: "bg-emerald-50 text-emerald-600 border-emerald-100",
    badgeVariant: "success",
  },
  "lead-intelligence": {
    id: "lead-intelligence",
    label: "Lead Intelligence",
    accent: "#7c3aed",
    accentHover: "#6d28d9",
    accentMuted: "#f5f3ff",
    accentBorder: "#ddd6fe",
    gradient: "from-violet-600 to-purple-600",
    iconClass: "bg-violet-50 text-violet-600 border-violet-100",
    badgeVariant: "primary",
  },
  "video-scraper": {
    id: "video-scraper",
    label: "Video Scraper",
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
