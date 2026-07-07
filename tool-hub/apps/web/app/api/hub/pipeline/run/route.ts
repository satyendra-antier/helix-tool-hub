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
    { id: "market-depth", label: "Refresh Market Depth", status: "pending" },
    { id: "build-readiness", label: "Run Fit Analysis", status: "pending" },
    { id: "lead-intelligence", label: "Discover Leads", status: "pending" },
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
      if (!refreshRes.ok) throw new Error("Market Depth refresh failed");
      const refreshJob = await refreshRes.json();
      if (refreshJob.job_id) {
        await pollJob("market-depth-analyzer", refreshJob.job_id, 120_000);
      }
      run.steps[0].status = "done";

      run.steps[1].status = "running";
      const analyzeRes = await fetchModule("build-readiness", "/analyze", { method: "POST" });
      if (!analyzeRes.ok) throw new Error("Fit Analysis failed to start");
      const analyzeJob = await analyzeRes.json();
      if (analyzeJob.job_id) {
        await pollJob("build-readiness", analyzeJob.job_id, 300_000);
      }
      run.steps[1].status = "done";

      run.steps[2].status = "running";
      const discoverRes = await fetchModule("lead-intelligence", "/discover", { method: "POST" });
      if (!discoverRes.ok) throw new Error("Lead discovery failed to start");
      const discoverJob = await discoverRes.json();
      if (discoverJob.job_id) {
        await pollJob("lead-intelligence", discoverJob.job_id, 300_000);
      }
      run.steps[2].status = "done";

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
    if (!res.ok) throw new Error(`Job ${jobId} not found`);
    const job = await res.json();
    if (job.status === "completed" || job.status === "done" || job.status === "success") return;
    if (job.status === "failed" || job.status === "error") {
      throw new Error(job.error || `Job ${jobId} failed`);
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`Job ${jobId} timed out`);
}
