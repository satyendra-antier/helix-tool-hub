import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions, isAdmin } from "@/lib/auth";
import { fetchModuleJson, getAllModuleSlugs } from "@/lib/module-api";

let cache: { data: unknown; at: number } | null = null;
const CACHE_MS = 30_000;

type HealthResult = { slug: string; ok: boolean; name: string };

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (cache && Date.now() - cache.at < CACHE_MS) {
    return NextResponse.json(cache.data);
  }

  const [
    marketSnapshots,
    buildPipeline,
    buildVerdicts,
    buildProfile,
    leadPipeline,
    leadCounts,
    videoJobs,
    marketConfig,
    buildConfig,
    leadConfig,
    videoConfig,
  ] = await Promise.all([
    fetchModuleJson<{ scores: Array<{ domain: string; composite_score: number; components?: Record<string, number> }>; fetched_at?: string }>(
      "market-depth-analyzer",
      "/snapshots/latest"
    ),
    fetchModuleJson<{ steps: Array<{ name: string; ready: boolean }> }>("build-readiness", "/pipeline/status"),
    fetchModuleJson<{ verdicts: Array<{ verdict: string; domain_name: string }> }>("build-readiness", "/verdicts/latest"),
    fetchModuleJson<{ chunks_indexed?: number; capabilities_count?: number; pages_indexed?: number; videos_indexed?: number }>(
      "build-readiness",
      "/profile"
    ),
    fetchModuleJson<{ steps: Array<{ name: string; ready: boolean }> }>("lead-intelligence", "/pipeline/status"),
    fetchModuleJson<{ total: number; leads: Array<{ stage?: string }> }>("lead-intelligence", "/leads?page_size=100"),
    fetchModuleJson<{ jobs: Array<{ id: string; status: string; title?: string; created_at?: string; source_url?: string }>; total: number }>(
      "video-scraper",
      "/jobs?limit=8"
    ),
    fetchModuleJson<Record<string, unknown>>("market-depth-analyzer", "/config"),
    fetchModuleJson<Record<string, unknown>>("build-readiness", "/config"),
    fetchModuleJson<Record<string, unknown>>("lead-intelligence", "/config"),
    fetchModuleJson<Record<string, unknown>>("video-scraper", "/config"),
  ]);

  const health: HealthResult[] = await Promise.all(
    getAllModuleSlugs().map(async (slug) => {
      const h = await fetchModuleJson<{ status: string }>(slug, "/health");
      return { slug, ok: h?.status === "ok", name: slug };
    })
  );

  const scores = marketSnapshots?.scores || [];
  const topDomain = scores[0];
  const verdicts = buildVerdicts?.verdicts || [];
  const goCount = verdicts.filter((v) => v.verdict === "GO").length;
  const conditionalCount = verdicts.filter((v) => v.verdict === "CONDITIONAL").length;
  const noGoCount = verdicts.filter((v) => v.verdict === "NO_GO").length;

  const stageCounts: Record<string, number> = {};
  for (const lead of leadCounts?.leads || []) {
    const stage = (lead as { pipeline_stage?: string }).pipeline_stage || "discovered";
    stageCounts[stage] = (stageCounts[stage] || 0) + 1;
  }

  const payload = {
    generatedAt: new Date().toISOString(),
    kpis: {
      topDomain: topDomain
        ? { name: topDomain.domain, score: topDomain.composite_score }
        : null,
      goVerdicts: { go: goCount, conditional: conditionalCount, noGo: noGoCount, total: verdicts.length },
      leadsInPipeline: leadCounts?.total || 0,
      proofAssets: {
        pages: buildProfile?.pages_indexed || 0,
        chunks: buildProfile?.chunks_indexed || 0,
        capabilities: buildProfile?.capabilities_count || 0,
        videos: buildProfile?.videos_indexed || 0,
      },
      marketFetchedAt: marketSnapshots?.fetched_at || null,
    },
    charts: {
      domainRankings: scores.slice(0, 12).map((s) => ({
        domain: s.domain,
        score: s.composite_score,
      })),
      verdictDistribution: [
        { name: "GO", value: goCount },
        { name: "CONDITIONAL", value: conditionalCount },
        { name: "NO_GO", value: noGoCount },
      ],
      leadFunnel: Object.entries(stageCounts).map(([stage, count]) => ({ stage, count })),
      topDomainSignals: topDomain?.components
        ? Object.entries(topDomain.components).map(([signal, value]) => ({ signal, value }))
        : [],
    },
    flywheel: {
      marketDepth: {
        ready: buildPipeline?.steps?.[0]?.ready ?? false,
        route: "/tools/market-depth-analyzer",
      },
      buildReadiness: {
        ready: buildPipeline?.steps?.[1]?.ready ?? false,
        route: "/tools/build-readiness",
      },
      leadIntelligence: {
        ready: leadPipeline?.steps?.[2]?.ready ?? false,
        route: "/tools/lead-intelligence",
      },
      videoScraper: {
        ready: (videoJobs?.total || 0) > 0,
        route: "/tools/video-scraper",
      },
    },
    activity: [
      ...(videoJobs?.jobs || []).map((j) => ({
        id: j.id,
        type: "video-scraper" as const,
        label: j.title || j.source_url || "Video job",
        status: j.status,
        at: j.created_at,
      })),
    ],
    health,
    integrations: {
      openai: !!(process.env.OPENAI_API_KEY || buildConfig),
      github: !!process.env.GITHUB_TOKEN,
      adzuna: !!(process.env.ADZUNA_APP_ID && process.env.ADZUNA_APP_KEY),
      hunter: !!process.env.HUNTER_API_KEY,
      marketConfig,
      buildConfig,
      leadConfig,
      videoConfig,
    },
    role: session.user.role,
    isAdmin: isAdmin(session.user.role),
  };

  cache = { data: payload, at: Date.now() };
  return NextResponse.json(payload);
}
