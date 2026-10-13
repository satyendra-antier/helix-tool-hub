import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { getPipelineConfig, writeAuditLog } from "@/lib/hub-db";
import { DEFAULT_PIPELINE_CONFIG } from "@tool-hub/shared-types";
import { fetchModule } from "@/lib/module-api";

const runs = new Map<string, {
  status: string;
  steps: Array<{ id: string; label: string; status: string; error?: string }>;
  startedAt: string;
  completedAt?: string;
}>();

export async function GET(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const runId = new URL(req.url).searchParams.get("runId");
  if (!runId) {
    return NextResponse.json({ error: "runId required" }, { status: 400 });
  }
  const run = runs.get(runId);
  if (!run) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }
  return NextResponse.json({ run });
}

export async function POST() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (session.user.role === "viewer") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const stored = await getPipelineConfig(session.user.orgId, "revenue-flywheel");
  const config = stored || DEFAULT_PIPELINE_CONFIG;
  const runId = crypto.randomUUID();
  const steps: Array<{ id: string; label: string; status: string; error?: string }> = [
    { id: "market-depth", label: "1 · Find Demand", status: "pending" },
    { id: "build-readiness", label: "2 · Check Fit", status: "pending" },
    { id: "lead-intelligence", label: "3 · Find Leads", status: "pending" },
    { id: "growth-pillars", label: "4 · Win Leads", status: "pending" },
    { id: "outreach-autopilot", label: "5 · Reach Out", status: "pending" },
  ];

  const run: {
    status: string;
    steps: Array<{ id: string; label: string; status: string; error?: string }>;
    startedAt: string;
    completedAt?: string;
  } = {
    status: "running",
    steps: [...steps],
    startedAt: new Date().toISOString(),
  };
  runs.set(runId, run);

  await writeAuditLog(session.user.orgId, session.user.id, "pipeline.run.start", { runId });

  (async () => {
    try {
      run.steps[0].status = "running";
      const mdConfig = (config as { nodes?: Record<string, unknown> }).nodes?.["market-depth"] as { weights?: Record<string, number> } | undefined;
      if (mdConfig?.weights) {
        await fetchModule("market-depth-analyzer", "/weights", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(mdConfig.weights),
        });
      }
      const refreshRes = await fetchModule("market-depth-analyzer", "/refresh", { method: "POST" });
      if (!refreshRes.ok) throw new Error("The market scan failed");
      const refreshJob = await refreshRes.json();
      if (refreshJob.job_id) {
        await pollJob("market-depth-analyzer", refreshJob.job_id, 600_000);
      }
      run.steps[0].status = "done";

      run.steps[1].status = "running";
      const analyzeRes = await fetchModule("build-readiness", "/analyze", { method: "POST" });
      if (!analyzeRes.ok) throw new Error("Check Fit could not start");
      const analyzeJob = await analyzeRes.json();
      if (analyzeJob.job_id) {
        await pollJob("build-readiness", analyzeJob.job_id, 1_200_000);
      }
      run.steps[1].status = "done";

      run.steps[2].status = "running";
      const discoverRes = await fetchModule("lead-intelligence", "/discover", { method: "POST" });
      if (!discoverRes.ok) throw new Error("Find Leads could not start");
      const discoverJob = await discoverRes.json();
      if (discoverJob.job_id) {
        await pollJob("lead-intelligence", discoverJob.job_id, 1_200_000);
      }
      run.steps[2].status = "done";

      run.steps[3].status = "running";
      const gpConfig = ((config as { nodes?: Record<string, unknown> }).nodes?.["growth-pillars"] ||
        DEFAULT_PIPELINE_CONFIG.nodes["growth-pillars"]) as {
        watchlistSize?: number;
        minLeadScore?: number;
        advisoryTopN?: number;
        rescoreLeads?: boolean;
      };
      const pillarsRes = await fetchModule("growth-pillars", "/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          watchlist_size: gpConfig.watchlistSize ?? 25,
          min_lead_score: gpConfig.minLeadScore ?? 40,
          advisory_top_n: gpConfig.advisoryTopN ?? 10,
          rescore_leads: gpConfig.rescoreLeads ?? true,
        }),
      });
      if (!pillarsRes.ok) throw new Error("Win Leads could not start");
      const pillarsJob = await pillarsRes.json();
      if (pillarsJob.job_id) {
        await pollJob("growth-pillars", pillarsJob.job_id, 600_000);
      }
      run.steps[3].status = "done";

      // Drafts only: first emails wait in the approval queue, nothing is sent from here.
      run.steps[4].status = "running";
      const outConfig = ((config as { nodes?: Record<string, unknown> }).nodes?.["outreach-autopilot"] ||
        DEFAULT_PIPELINE_CONFIG.nodes["outreach-autopilot"]) as { draftForTopN?: number; minLeadScore?: number };
      const outreachRes = await fetchModule("outreach-autopilot", "/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draftForTopN: outConfig.draftForTopN ?? 10,
          minLeadScore: outConfig.minLeadScore ?? 60,
        }),
      });
      if (!outreachRes.ok) throw new Error("Reach Out could not start");
      const outreachJob = await outreachRes.json();
      if (outreachJob.job_id) {
        await pollJob("outreach-autopilot", outreachJob.job_id, 900_000);
      }
      run.steps[4].status = "done";

      run.status = "completed";
      run.completedAt = new Date().toISOString();
      await writeAuditLog(session.user.orgId, session.user.id, "pipeline.run.complete", { runId });
    } catch (err) {
      const step = run.steps.find((s) => s.status === "running") || run.steps.find((s) => s.status === "pending");
      if (step) {
        step.status = "error";
        step.error = err instanceof Error ? err.message : "Unknown error";
      }
      run.status = "failed";
      run.completedAt = new Date().toISOString();
      await writeAuditLog(session.user.orgId, session.user.id, "pipeline.run.failed", {
        runId,
        error: err instanceof Error ? err.message : "Unknown",
      });
    }
  })();

  return NextResponse.json({ runId, status: "running" });
}

async function pollJob(slug: string, jobId: string, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await fetchModule(slug, `/jobs/${jobId}`);
    if (!res.ok) throw new Error("The service lost track of this run.");
    const job = await res.json();
    if (job.status === "completed" || job.status === "done" || job.status === "success") return;
    if (job.status === "failed" || job.status === "error") {
      throw new Error(String(job.error || "This step failed.").split("\n")[0]);
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(`Took longer than ${Math.round(timeoutMs / 60_000)} minutes.`);
}
