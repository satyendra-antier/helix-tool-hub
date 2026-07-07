/** Chart and visualization colors — keep in sync with tailwind theme */
export const chartColors = {
  primary: "#4f46e5",
  secondary: "#6366f1",
  success: "#059669",
  warning: "#d97706",
  danger: "#dc2626",
  muted: "#a1a1aa",
  indigo: "#4f46e5",
  emerald: "#059669",
  amber: "#d97706",
  violet: "#7c3aed",
  slate: "#64748b",
} as const;

export const trackColors: Record<string, string> = {
  blockchain: chartColors.indigo,
  ai: chartColors.violet,
  content: chartColors.amber,
  intelligence: chartColors.emerald,
  growth: chartColors.success,
};

export const fitColors: Record<string, string> = {
  GO: chartColors.success,
  CONDITIONAL: chartColors.warning,
  NO_GO: chartColors.danger,
  PENDING: chartColors.muted,
};
