import { z } from "zod";
import { DEFAULT_WEIGHTS } from "./signals";

export const PipelineTemplateIdSchema = z.enum(["revenue-flywheel"]);
export type PipelineTemplateId = z.infer<typeof PipelineTemplateIdSchema>;

export const MarketDepthNodeConfigSchema = z.object({
  domains: z.array(z.string()).default([]),
  weights: z.record(z.number()).default({ ...DEFAULT_WEIGHTS }),
  enabledSources: z
    .array(z.enum(["hiring", "capital", "github", "funding", "interest"]))
    .default(["hiring", "capital", "github", "funding", "interest"]),
  refreshCadence: z.enum(["weekly", "manual"]).default("manual"),
});

export const BuildReadinessNodeConfigSchema = z.object({
  websiteUrls: z.array(z.string()).default([]),
  analyzeDomains: z.union([z.literal("from-market"), z.array(z.string())]).default("from-market"),
});

export const LeadIntelligenceNodeConfigSchema = z.object({
  minMarketScore: z.number().min(0).max(100).default(40),
  minVerdict: z.enum(["GO", "CONDITIONAL", "NO_GO"]).default("CONDITIONAL"),
  orientations: z.array(z.enum(["demand", "future"])).default(["demand", "future"]),
});

export const VideoScraperNodeConfigSchema = z.object({
  channelUrls: z.array(z.string()).default([]),
  enrichBuildReadiness: z.boolean().default(true),
});

export const GrowthPillarsNodeConfigSchema = z.object({
  watchlistSize: z.number().min(1).max(200).default(25),
  minLeadScore: z.number().min(0).max(100).default(40),
  advisoryTopN: z.number().min(0).max(50).default(10),
  rescoreLeads: z.boolean().default(true),
});

export const OutreachNodeConfigSchema = z.object({
  draftForTopN: z.number().min(0).max(100).default(10),
  minLeadScore: z.number().min(0).max(100).default(60),
});

export const PipelineNodeConfigSchema = z.union([
  MarketDepthNodeConfigSchema,
  BuildReadinessNodeConfigSchema,
  LeadIntelligenceNodeConfigSchema,
  VideoScraperNodeConfigSchema,
  GrowthPillarsNodeConfigSchema,
  OutreachNodeConfigSchema,
]);

export const PipelineConfigSchema = z.object({
  templateId: PipelineTemplateIdSchema,
  nodes: z.record(z.string(), z.unknown()),
  updatedAt: z.string().optional(),
});

export type PipelineConfig = z.infer<typeof PipelineConfigSchema>;
export type MarketDepthNodeConfig = z.infer<typeof MarketDepthNodeConfigSchema>;
export type BuildReadinessNodeConfig = z.infer<typeof BuildReadinessNodeConfigSchema>;
export type LeadIntelligenceNodeConfig = z.infer<typeof LeadIntelligenceNodeConfigSchema>;
export type VideoScraperNodeConfig = z.infer<typeof VideoScraperNodeConfigSchema>;
export type GrowthPillarsNodeConfig = z.infer<typeof GrowthPillarsNodeConfigSchema>;
export type OutreachNodeConfig = z.infer<typeof OutreachNodeConfigSchema>;

export const DEFAULT_PIPELINE_CONFIG: PipelineConfig = {
  templateId: "revenue-flywheel",
  nodes: {
    "market-depth": {
      domains: [],
      weights: { ...DEFAULT_WEIGHTS },
      enabledSources: ["hiring", "capital", "github", "funding", "interest"],
      refreshCadence: "manual",
    },
    "build-readiness": {
      websiteUrls: [],
      analyzeDomains: "from-market",
    },
    "lead-intelligence": {
      minMarketScore: 40,
      minVerdict: "CONDITIONAL",
      orientations: ["demand", "future"],
    },
    "video-scraper": {
      channelUrls: [],
      enrichBuildReadiness: true,
    },
    "growth-pillars": {
      watchlistSize: 25,
      minLeadScore: 40,
      advisoryTopN: 10,
      rescoreLeads: true,
    },
    "outreach-autopilot": {
      draftForTopN: 10,
      minLeadScore: 60,
    },
  },
};

export type PipelineRunStep = {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  error?: string;
};

export type PipelineRunState = {
  runId: string;
  status: "running" | "completed" | "failed";
  steps: PipelineRunStep[];
  startedAt: string;
  completedAt?: string;
};
