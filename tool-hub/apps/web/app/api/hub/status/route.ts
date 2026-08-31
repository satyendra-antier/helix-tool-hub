import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions, isAdmin } from "@/lib/auth";
import { fetchModuleJson, getAllModuleSlugs } from "@/lib/module-api";

let cache: { data: unknown; at: number } | null = null;
const CACHE_MS = 30_000;

type HealthResult = { slug: string; ok: boolean; name: string };

type PipelineStep = {
  name: string;
  ready: boolean;
  latest_at?: string | null;
  stats?: Record<string, number | string | null>;
};

function maxIso(dates: Array<string | null | undefined>): string | null {
  const parsed = dates
    .filter((d): d is string => !!d)
    .map((d) => ({ d, t: Date.parse(d) }))
    .filter((x) => !Number.isNaN(x.t))
    .sort((a, b) => b.t - a.t);
  return parsed[0]?.d ?? null;
}

function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

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
    fetchModuleJson<{
      scores: Array<{ domain: string; composite_score: number; components?: Record<string, number> }>;
      fetched_at?: string;
    }>("market-depth-analyzer", "/snapshots/latest"),
    fetchModuleJson<{
      steps: PipelineStep[];
      stale_warning?: string | null;
    }>("build-readiness", "/pipeline/status"),
    fetchModuleJson<{
      verdicts: Array<{ verdict: string; domain_name: string; analyzed_at?: string }>;
    }>("build-readiness", "/verdicts/latest"),
    fetchModuleJson<{
      chunks_indexed?: number;
      capabilities_count?: number;
      pages_indexed?: number;
      videos_indexed?: number;
      last_indexed_at?: string;
    }>("build-readiness", "/profile"),
    fetchModuleJson<{ steps: PipelineStep[]; stale_warning?: string | null }>(
      "lead-intelligence",
      "/pipeline/status"
    ),
    // Small page — stage counts for funnel; avoid loading 100×N+1 contacts
    fetchModuleJson<{ total: number; leads: Array<{ stage?: string }> }>(
      "lead-intelligence",
      "/leads?page_size=50&sort=score",
      { timeoutMs: 10_000 }
    ),
    fetchModuleJson<{
      jobs: Array<{ id: string; status: string; title?: string; created_at?: string; source_url?: string }>;
      total: number;
    }>("video-scraper", "/jobs?limit=8"),
    fetchModuleJson<Record<string, unknown>>("market-depth-analyzer", "/config"),
    fetchModuleJson<Record<string, unknown>>("build-readiness", "/config"),
    fetchModuleJson<Record<string, unknown>>("lead-intelligence", "/config"),
    fetchModuleJson<Record<string, unknown>>("video-scraper", "/config"),
  ]);

  const health: HealthResult[] = await Promise.all(
    getAllModuleSlugs().map(async (slug) => {
      const h = await fetchModuleJson<{ status: string }>(slug, "/health", { timeoutMs: 4_000 });
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
    const stage = lead.stage || "new";
    stageCounts[stage] = (stageCounts[stage] || 0) + 1;
  }

  const marketAt = marketSnapshots?.fetched_at || buildPipeline?.steps?.[0]?.latest_at || null;
  const companyAt =
    buildProfile?.last_indexed_at || buildPipeline?.steps?.[1]?.latest_at || null;
  const fitAt = buildPipeline?.steps?.[2]?.latest_at || null;
  const dataAsOf = maxIso([marketAt, companyAt, fitAt]);
  const fitAgeDays = daysSince(fitAt);
  const marketAgeDays = daysSince(marketAt);

  const freshnessWarnings: string[] = [];
  if (buildPipeline?.stale_warning) freshnessWarnings.push(buildPipeline.stale_warning);
  if (fitAgeDays != null && fitAgeDays > 7) {
    freshnessWarnings.push(
      `Fit Verdict is ${fitAgeDays} day(s) old` + (fitAt ? ` (last run ${new Date(fitAt).toLocaleDateString()})` : "")
    );
  }
  if (marketAgeDays != null && fitAgeDays != null && marketAgeDays < fitAgeDays) {
    freshnessWarnings.push("Market data is newer than Fit Verdict — re-run Build Readiness analysis");
  }

  const payload = {
    generatedAt: new Date().toISOString(),
    dataAsOf,
    freshness: {
      marketAt,
      companyDepthAt: companyAt,
      fitVerdictAt: fitAt,
      staleWarning: freshnessWarnings.length ? freshnessWarnings.join(" · ") : null,
      fitAgeDays,
    },
    kpis: {
      topDomain: topDomain
        ? { name: topDomain.domain, score: topDomain.composite_score }
        : null,
      goVerdicts: {
        go: goCount,
        conditional: conditionalCount,
        noGo: noGoCount,
        total: verdicts.length,
        asOf: fitAt,
      },
      leadsInPipeline: leadCounts?.total || 0,
      proofAssets: {
        pages: buildProfile?.pages_indexed || 0,
        chunks: buildProfile?.chunks_indexed || 0,
        capabilities: buildProfile?.capabilities_count || 0,
        videos: buildProfile?.videos_indexed || 0,
      },
      marketFetchedAt: marketAt,
    },
    charts: {
      // Reverse so Recharts vertical layout paints #1 at the TOP (not bottom)
      domainRankings: [...scores.slice(0, 12)]
        .reverse()
        .map((s) => ({
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
        latestAt: marketAt,
      },
      buildReadiness: {
        // Fit Verdict (step 3), not Company Depth (step 2)
        ready: buildPipeline?.steps?.[2]?.ready ?? false,
        route: "/tools/build-readiness",
        latestAt: fitAt,
      },
      leadIntelligence: {
        ready: leadPipeline?.steps?.[2]?.ready ?? (leadCounts?.total || 0) > 0,
        route: "/tools/lead-intelligence",
      },
      videoScraper: {
        ready: (videoJobs?.jobs || []).some((j) => j.status === "done" || j.status === "partial"),
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
