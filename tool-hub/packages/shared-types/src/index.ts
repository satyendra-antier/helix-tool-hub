import { z } from "zod";

export const ToolManifestSchema = z.object({
  id: z.string(),
  name: z.string(),
  tagline: z.string(),
  icon: z.string(),
  route: z.string(),
  backendBaseUrl: z.string(),
  status: z.enum(["active", "beta", "deprecated"]),
  requiredEnv: z.array(z.string()),
  category: z.string(),
  version: z.string(),
});

export type ToolManifest = z.infer<typeof ToolManifestSchema>;

export const VideoSummarySchema = z.object({
  one_line_summary: z.string(),
  key_points: z.array(z.string()),
  chapters: z.array(
    z.object({
      timestamp_hint: z.string(),
      title: z.string(),
    })
  ),
  notable_quotes: z.array(z.string()),
  topics: z.array(z.string()),
});

export type VideoSummary = z.infer<typeof VideoSummarySchema>;

export const DEFAULT_WEIGHTS = {
  hiring_demand: 0.3,
  capital_flow: 0.25,
  developer_momentum: 0.2,
  funding_signal: 0.15,
  public_interest: 0.1,
} as const;

export type WeightKey = keyof typeof DEFAULT_WEIGHTS;
