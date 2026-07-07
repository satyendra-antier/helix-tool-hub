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

export { DEFAULT_WEIGHTS, type WeightKey } from "./signals";

export * from "./hub";
export * from "./pipeline";
export * from "./connectors";
