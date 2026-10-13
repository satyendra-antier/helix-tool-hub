"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  Label,
  Progress,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Skeleton,
} from "@tool-hub/ui";

type PipelineStep = {
  step: number;
  name: string;
  description: string;
  ready: boolean;
  latest_at: string | null;
  action: string;
  tool_route?: string;
};

type PipelineStatus = {
  steps: PipelineStep[];
  can_analyze: boolean;
  stale_warning: string | null;
};

type Profile = {
  company_name: string;
  website_url: string;
  last_indexed_at: string | null;
  pages_indexed: number;
  chunks_indexed: number;
  capabilities_count?: number;
  videos_indexed: number;
};

type Verdict = {
  domain_name: string;
  track: string;
  verdict: "GO" | "CONDITIONAL" | "NO_GO" | "PENDING";
  status?: "done" | "pending" | "processing";
  market_score: number;
  capability_score: number;
  opportunity_score: number;
  verdict_detail: {
    headline?: string;
    can_build?: boolean;
    market_need?: string;
    our_strengths?: string[];
    gaps?: string[];
    strengthen_suggestions?: string[];
    how_to_build?: { phase_1?: string; phase_2?: string; phase_3?: string };
    revenue_path?: string;
    depth_assessment?: string;
  };
  citations: { url?: string; title?: string; excerpt?: string; source_type?: string }[];
};

type AnalyzeProgress = {
  domains?: number;
  domains_done?: number;
  current_domain?: string;
};

const VERDICT_BADGE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  GO: "success",
  CONDITIONAL: "warning",
  NO_GO: "danger",
  PENDING: "muted",
};

function fmtTime(iso: string | null | undefined) {
  if (!iso) return "Not yet";
  return new Date(iso).toLocaleString();
}

export default function BuildReadinessPanel() {
  const { backendUrl } = useToolContext();
  const apiBase = backendUrl;

  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [capabilities, setCapabilities] = useState<Record<string, { name: string; depth_score: number }[]>>({});
  const [selected, setSelected] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ analyzed_at?: string; market_fetched_at?: string; company_indexed_at?: string; go_count?: number }>({});
  const [apiConfigured, setApiConfigured] = useState(true);
  const [missingDomains, setMissingDomains] = useState<string[]>([]);
  const [analyzeProgress, setAnalyzeProgress] = useState<AnalyzeProgress | null>(null);
  const [totalDomains, setTotalDomains] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoadError(null);
      const [pRes, vRes, cRes, sRes, cfgRes, domRes] = await Promise.all([
        fetch(`${apiBase}/profile`),
        fetch(`${apiBase}/verdicts/latest`),
        fetch(`${apiBase}/capabilities`),
        fetch(`${apiBase}/pipeline/status`),
        fetch(`${apiBase}/config`),
        fetch(`${apiBase}/domains/status`),
      ]);
      const p = await pRes.json();
      const v = await vRes.json();
      const c = await cRes.json();
      const s = await sRes.json();
      const cfg = await cfgRes.json();
      const dom = await domRes.json();
      setProfile(p);
      setCompanyName(p.company_name || "");
      setWebsiteUrl(p.website_url || "");
      setVerdicts(v.verdicts || []);
      setMeta({
        analyzed_at: v.analyzed_at,
        market_fetched_at: v.market_fetched_at,
        company_indexed_at: v.company_indexed_at,
        go_count: v.go_count,
      });
      setCapabilities(c.categories || {});
      setPipeline(s);
      setApiConfigured(cfg.openai_configured !== false);
      setMissingDomains(dom.missing_verdicts || []);
      setAnalyzeProgress(v.analyze_progress || null);
      setTotalDomains(v.total_domains || (v.verdicts || []).length);
      if (v.analyze_in_progress && busy !== "analyzing") setBusy("analyzing");
    } catch {
      setLoadError("Couldn't load Check Fit results. The service may still be starting, try again in a minute.");
    } finally {
      setLoading(false);
    }
  }, [apiBase, busy]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      const res = await fetch(`${apiBase}/jobs/${jobId}`);
      const job = await res.json();
      if (job.job_type === "analyze" || job.status === "analyzing") {
        setAnalyzeProgress(job.progress || null);
        load();
      }
      if (job.status === "done" || job.status === "failed") {
        setBusy(null);
        setJobId(null);
        setAnalyzeProgress(null);
        if (job.status === "failed") setJobError(job.error || "Job failed");
        load();
        clearInterval(interval);
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [jobId, apiBase, load]);

  const saveProfile = async () => {
    await fetch(`${apiBase}/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: companyName, website_url: websiteUrl }),
    });
    load();
  };

  const runJob = async (path: string, label: string) => {
    setJobError(null);
    setBusy(label);
    let res: Response;
    try {
      res = await fetch(`${apiBase}${path}`, { method: "POST" });
    } catch {
      setJobError("Couldn't reach the Check Fit service. It may still be starting, try again in a minute.");
      setBusy(null);
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setJobError(err.detail || "Request failed");
      setBusy(null);
      return;
    }
    const data = await res.json();
    setJobId(data.job_id);
    if (path.includes("/analyze")) load();
  };

  const goCount = meta.go_count ?? verdicts.filter((v) => v.verdict === "GO").length;
  const completedVerdicts = verdicts.filter((v) => v.verdict !== "PENDING");
  const isAnalyzing = busy === "analyzing" || !!analyzeProgress?.domains;
  const progressPct = analyzeProgress?.domains
    ? Math.round(((analyzeProgress.domains_done ?? 0) / analyzeProgress.domains) * 100)
    : 0;

  const topCaps = Object.entries(capabilities)
    .flatMap(([cat, items]) => items.map((i) => ({ ...i, cat })))
    .sort((a, b) => b.depth_score - a.depth_score)
    .slice(0, 14);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {loadError && <Alert variant="danger" title="Load error">{loadError}</Alert>}
      {jobError && <Alert variant="danger" title="Job failed">{jobError}</Alert>}

      <Card className="accent-strip">
        <CardHeader>
          <CardTitle>Pipeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {pipeline?.stale_warning && (
            <Alert variant="warning" title="Data may be stale">{pipeline.stale_warning}</Alert>
          )}
          {!apiConfigured && (
            <Alert variant="danger" title="API key required">
              Set OPENAI_API_KEY in .env and restart services.
            </Alert>
          )}
          {missingDomains.length > 0 && !isAnalyzing && (
            <Alert variant="warning" title={`${missingDomains.length} market(s) not checked yet`}>
              <p className="mb-3">{missingDomains.join(", ")}</p>
              <Button size="sm" onClick={() => runJob("/analyze", "analyzing")} disabled={!!busy || !pipeline?.can_analyze}>
                Check our fit
              </Button>
            </Alert>
          )}
          {isAnalyzing && analyzeProgress?.domains && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-text-secondary">
                <span>AI is checking our fit · {analyzeProgress.domains_done ?? 0}/{analyzeProgress.domains} markets</span>
                <span>{progressPct}%</span>
              </div>
              <Progress value={progressPct} />
              {analyzeProgress.current_domain && (
                <p className="text-xs text-text-muted truncate">Analyzing: {analyzeProgress.current_domain}</p>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {pipeline?.steps.map((step) => (
              <div
                key={step.step}
                className={`rounded-lg border p-4 ${step.ready ? "border-success/30 bg-success/5" : "border-border bg-surface-muted"}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  {step.ready ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <Circle className="h-4 w-4 text-text-muted" />
                  )}
                  <span className="text-xs text-text-muted">Step {step.step}</span>
                </div>
                <h4 className="font-medium text-sm text-text-primary">{step.name}</h4>
                <p className="text-xs text-text-secondary mt-1">{step.description}</p>
                <p className="text-xs text-text-muted mt-2">Updated: {fmtTime(step.latest_at)}</p>
                {step.tool_route ? (
                  <Link href={step.tool_route} className="text-xs text-primary mt-2 inline-block hover:underline">
                    {step.action} →
                  </Link>
                ) : (
                  <p className="text-xs text-text-secondary mt-2">{step.action}</p>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your company</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="company">Company name</Label>
              <Input id="company" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Your company" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Website URL</Label>
              <Input id="website" value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} placeholder="https://example.com" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={saveProfile} disabled={!!busy}>Save</Button>
            <Button onClick={() => runJob("/index/website", "indexing")} disabled={!!busy || !apiConfigured}>
              {busy === "indexing" ? <><Loader2 className="h-4 w-4 animate-spin" /> Reading website…</> : "Read our website"}
            </Button>
            <Button variant="secondary" onClick={() => runJob("/index/website?full=true", "full-index")} disabled={!!busy || !apiConfigured}>
              {busy === "full-index" ? "Re-reading…" : "Re-read whole website"}
            </Button>
            <Button variant="outline" onClick={() => runJob("/index/videos", "videos")} disabled={!!busy || !apiConfigured}>
              {busy === "videos" ? "Adding videos…" : "Add Proof Library videos"}
            </Button>
            <Button variant="secondary" onClick={() => runJob("/analyze", "analyzing")} disabled={!!busy || !pipeline?.can_analyze || !apiConfigured}>
              {busy === "analyzing" ? "AI is checking…" : missingDomains.length ? `Check our fit (${missingDomains.length} markets)` : "Check our fit"}
            </Button>
          </div>
          {profile && (
            <p className="text-xs text-text-muted">
              {profile.pages_indexed} pages · {profile.chunks_indexed} chunks · {profile.capabilities_count ?? topCaps.length} capabilities · {profile.videos_indexed} videos
              {profile.last_indexed_at && ` · indexed ${fmtTime(profile.last_indexed_at)}`}
            </p>
          )}
          <p className="text-xs text-text-secondary">
            First let AI read your website so it knows what you build. Then press "Check our fit" to get a GO / maybe / no answer for each market.
          </p>
        </CardContent>
      </Card>

      {topCaps.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Company depth</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {topCaps.map((c, i) => (
                <Badge key={i} variant="outline">
                  {c.name} <span className="font-mono ml-1 text-primary">{c.depth_score.toFixed(0)}</span>
                  <span className="text-text-muted ml-1">({c.cat})</span>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {verdicts.length > 0 ? (
        <div>
          <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
            <h3 className="text-sm font-medium text-text-primary">
              Fit verdicts · {goCount} GO · {completedVerdicts.length}/{totalDomains || verdicts.length} domains
            </h3>
            <div className="text-xs text-text-muted text-right">
              <div>Analysis: {fmtTime(meta.analyzed_at)}</div>
              <div>Market: {fmtTime(meta.market_fetched_at)} · Index: {fmtTime(meta.company_indexed_at)}</div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {verdicts.map((v) => {
              const isPending = v.verdict === "PENDING";
              return (
                <button
                  key={v.domain_name}
                  onClick={() => !isPending && setSelected(v)}
                  disabled={isPending}
                  className={`text-left rounded-xl border p-4 bg-surface transition-all ${
                    isPending ? "border-dashed opacity-70 cursor-default" : "hover:shadow-md hover:border-primary/30"
                  } ${v.status === "processing" ? "ring-2 ring-primary/20" : ""}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <Badge variant={VERDICT_BADGE[v.verdict] || "muted"}>
                      {isPending ? (v.status === "processing" ? "Analyzing…" : "Pending") : v.verdict}
                    </Badge>
                    {!isPending && (
                      <span className="text-xs font-mono text-text-muted">{v.opportunity_score.toFixed(0)}</span>
                    )}
                  </div>
                  <h4 className="font-medium text-sm text-text-primary">{v.domain_name}</h4>
                  <p className="text-xs text-text-muted mt-1">{v.track}</p>
                  <div className="flex gap-3 mt-2 text-xs text-text-secondary">
                    <span>Market {v.market_score.toFixed(0)}</span>
                    {!isPending && <span>Depth {v.capability_score.toFixed(0)}</span>}
                  </div>
                  {v.verdict_detail?.headline && (
                    <p className="text-xs text-text-secondary mt-2 line-clamp-2">{v.verdict_detail.headline}</p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <EmptyState
          title="No verdicts yet"
          description='Run step 1 (Find Demand), let AI read your website, then press "Check our fit".'
        />
      )}

      <Sheet open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent>
          {selected && (
            <>
              <SheetHeader>
                <Badge variant={VERDICT_BADGE[selected.verdict]} className="mb-2 w-fit">
                  {selected.verdict}
                </Badge>
                <SheetTitle>{selected.domain_name}</SheetTitle>
                <p className="text-xs text-text-muted">
                  Market {selected.market_score.toFixed(0)} · Depth {selected.capability_score.toFixed(0)} ·
                  Can build: {selected.verdict_detail?.can_build ? "Yes" : "Gaps remain"}
                </p>
              </SheetHeader>
              <div className="mt-6 space-y-5 overflow-y-auto max-h-[calc(100vh-8rem)] pr-2">
                <section>
                  <h4 className="text-xs font-medium text-text-muted uppercase mb-2">Market need</h4>
                  <p className="text-sm text-text-secondary">{selected.verdict_detail?.market_need}</p>
                </section>
                <section>
                  <h4 className="text-xs font-medium text-text-muted uppercase mb-2">Strengths</h4>
                  <ul className="text-sm text-text-secondary space-y-1">
                    {(selected.verdict_detail?.our_strengths || []).map((s, i) => (
                      <li key={i} className="flex gap-2"><span className="text-success">✓</span>{s}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h4 className="text-xs font-medium text-text-muted uppercase mb-2">Gaps</h4>
                  <ul className="text-sm text-text-secondary space-y-1">
                    {(selected.verdict_detail?.gaps || []).map((g, i) => (
                      <li key={i} className="flex gap-2"><span className="text-warning">!</span>{g}</li>
                    ))}
                  </ul>
                </section>
                {(selected.verdict_detail?.strengthen_suggestions?.length ?? 0) > 0 && (
                  <Alert variant={selected.verdict === "NO_GO" ? "danger" : "warning"} title="Recommendations">
                    <ul className="space-y-1 mt-1">
                      {selected.verdict_detail!.strengthen_suggestions!.map((s, i) => (
                        <li key={i}>{i + 1}. {s}</li>
                      ))}
                    </ul>
                  </Alert>
                )}
                <section>
                  <h4 className="text-xs font-medium text-text-muted uppercase mb-2">How to build</h4>
                  <div className="text-sm text-text-secondary space-y-2">
                    {selected.verdict_detail?.how_to_build?.phase_1 && <p><b>Phase 1:</b> {selected.verdict_detail.how_to_build.phase_1}</p>}
                    {selected.verdict_detail?.how_to_build?.phase_2 && <p><b>Phase 2:</b> {selected.verdict_detail.how_to_build.phase_2}</p>}
                    {selected.verdict_detail?.how_to_build?.phase_3 && <p><b>Phase 3:</b> {selected.verdict_detail.how_to_build.phase_3}</p>}
                  </div>
                </section>
                <section>
                  <h4 className="text-xs font-medium text-text-muted uppercase mb-2">Evidence</h4>
                  <div className="space-y-2">
                    {selected.citations.map((c, i) => (
                      <div key={i} className="border border-border rounded-lg p-3 text-xs">
                        <p className="font-medium text-text-primary truncate">{c.title || c.url}</p>
                        <p className="text-text-muted mt-1 line-clamp-3">{c.excerpt}</p>
                        {c.url && (
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-primary mt-1 inline-block hover:underline">
                            View source
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
