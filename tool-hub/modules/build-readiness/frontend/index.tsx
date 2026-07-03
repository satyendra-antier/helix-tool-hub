"use client";

import { useCallback, useEffect, useState } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";

type Profile = {
  company_name: string;
  website_url: string;
  last_indexed_at: string | null;
  pages_indexed: number;
  chunks_indexed: number;
  videos_indexed: number;
};

type Verdict = {
  domain_name: string;
  track: string;
  verdict: "GO" | "CONDITIONAL" | "NO_GO";
  market_score: number;
  capability_score: number;
  opportunity_score: number;
  verdict_detail: {
    headline?: string;
    can_build?: boolean;
    confidence?: string;
    market_need?: string;
    our_strengths?: string[];
    gaps?: string[];
    how_to_build?: { phase_1?: string; phase_2?: string; phase_3?: string };
    revenue_path?: string;
    depth_assessment?: string;
    matched_capabilities?: string[];
  };
  citations: { url?: string; title?: string; excerpt?: string; source_type?: string }[];
};

const VERDICT_COLORS = {
  GO: { bg: "bg-ok/10", text: "text-ok", border: "border-ok/40" },
  CONDITIONAL: { bg: "bg-yellow-950/30", text: "text-yellow-400", border: "border-yellow-700/50" },
  NO_GO: { bg: "bg-red-950/30", text: "text-red-400", border: "border-red-800/50" },
};

export default function BuildReadinessPanel() {
  const { backendUrl } = useToolContext();
  const apiBase =
    typeof window !== "undefined"
      ? backendUrl.replace("build-readiness-api", "localhost")
      : backendUrl;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [companyName, setCompanyName] = useState("Antier");
  const [websiteUrl, setWebsiteUrl] = useState("https://www.antier.com/");
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [capabilities, setCapabilities] = useState<Record<string, { name: string; depth_score: number }[]>>({});
  const [selected, setSelected] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [analyzedAt, setAnalyzedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [pRes, vRes, cRes] = await Promise.all([
        fetch(`${apiBase}/profile`),
        fetch(`${apiBase}/verdicts/latest`),
        fetch(`${apiBase}/capabilities`),
      ]);
      const p = await pRes.json();
      const v = await vRes.json();
      const c = await cRes.json();
      setProfile(p);
      setCompanyName(p.company_name);
      setWebsiteUrl(p.website_url);
      setVerdicts(v.verdicts || []);
      setAnalyzedAt(v.analyzed_at);
      setCapabilities(c.categories || {});
    } catch {
      /* ignore */
    }
  }, [apiBase]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      const res = await fetch(`${apiBase}/jobs/${jobId}`);
      const job = await res.json();
      if (job.status === "done" || job.status === "failed") {
        setBusy(null);
        setJobId(null);
        if (job.status === "failed") alert(job.error || "Job failed");
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
    setBusy(label);
    const res = await fetch(`${apiBase}${path}`, { method: "POST" });
    const data = await res.json();
    setJobId(data.job_id);
  };

  const goCount = verdicts.filter((v) => v.verdict === "GO").length;
  const topCaps = Object.entries(capabilities)
    .flatMap(([cat, items]) => items.map((i) => ({ ...i, cat })))
    .sort((a, b) => b.depth_score - a.depth_score)
    .slice(0, 12);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-accent-b/10 text-accent-b border border-accent-b/30">
          RAG + market depth
        </span>
        <span className="font-mono text-[10px] text-text-dim">
          index company site → match capabilities → verdict per domain
        </span>
      </div>

      {/* Company config */}
      <div className="bg-panel border border-border rounded-lg p-5">
        <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-4">Company Profile</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="font-mono text-[10px] text-text-dim uppercase">Company name</label>
            <input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full mt-1 bg-panel-raised border border-border rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] text-text-dim uppercase">Website URL</label>
            <input
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              placeholder="https://www.antier.com/"
              className="w-full mt-1 bg-panel-raised border border-border rounded px-3 py-2 text-sm font-mono"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={saveProfile} className="font-mono text-xs border border-border px-4 py-2 rounded hover:border-border-bright">
            Save config
          </button>
          <button
            onClick={() => runJob("/index/website", "indexing")}
            disabled={!!busy}
            className="font-mono text-xs bg-accent-b text-bg px-4 py-2 rounded hover:opacity-90 disabled:opacity-40"
          >
            {busy === "indexing" ? "Indexing website…" : "Index Website"}
          </button>
          <button
            onClick={() => runJob("/index/videos", "videos")}
            disabled={!!busy}
            className="font-mono text-xs border border-accent-a/50 text-accent-a px-4 py-2 rounded hover:bg-accent-a/10 disabled:opacity-40"
          >
            {busy === "videos" ? "Indexing videos…" : "Index Video Transcripts"}
          </button>
          <button
            onClick={() => runJob("/analyze", "analyzing")}
            disabled={!!busy}
            className="font-mono text-xs bg-ok/20 text-ok border border-ok/40 px-4 py-2 rounded hover:bg-ok/30 disabled:opacity-40"
          >
            {busy === "analyzing" ? "Analyzing…" : "Run Fit Analysis"}
          </button>
        </div>
        {profile && (
          <p className="font-mono text-[10px] text-text-dim mt-3">
            Indexed: {profile.pages_indexed} pages · {profile.chunks_indexed} chunks · {profile.videos_indexed} videos
            {profile.last_indexed_at && ` · last index ${new Date(profile.last_indexed_at).toLocaleString()}`}
          </p>
        )}
      </div>

      {/* Company depth summary */}
      {topCaps.length > 0 && (
        <div className="bg-panel border border-border rounded-lg p-5">
          <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-3">
            Your Depth (from indexed site)
          </h3>
          <div className="flex flex-wrap gap-2">
            {topCaps.map((c, i) => (
              <span key={i} className="font-mono text-[10px] px-2 py-1 rounded border border-border bg-panel-raised">
                {c.name} <span className="text-accent-b">{c.depth_score.toFixed(0)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Verdict matrix */}
      {verdicts.length > 0 ? (
        <div>
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider">
              Build Verdicts · {goCount} GO · {verdicts.length} domains
            </h3>
            {analyzedAt && (
              <span className="font-mono text-[10px] text-text-dim">
                analyzed {new Date(analyzedAt).toLocaleString()}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {verdicts.map((v) => {
              const style = VERDICT_COLORS[v.verdict] || VERDICT_COLORS.CONDITIONAL;
              return (
                <button
                  key={v.domain_name}
                  onClick={() => setSelected(v)}
                  className={`text-left border rounded-lg p-4 hover:border-border-bright transition-colors ${style.bg} ${style.border}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className={`font-mono text-[10px] font-bold ${style.text}`}>{v.verdict}</span>
                    <span className="font-mono text-xs text-text-dim">{v.opportunity_score.toFixed(0)}</span>
                  </div>
                  <h4 className="font-display font-semibold text-sm">{v.domain_name}</h4>
                  <p className="font-mono text-[10px] text-text-dim mt-1">{v.track}</p>
                  <div className="flex gap-3 mt-2 font-mono text-[10px]">
                    <span>market {v.market_score.toFixed(0)}</span>
                    <span>depth {v.capability_score.toFixed(0)}</span>
                  </div>
                  {v.verdict_detail?.headline && (
                    <p className="text-text-secondary text-xs mt-2 line-clamp-2">{v.verdict_detail.headline}</p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="bg-panel border border-dashed border-border rounded-lg p-8 text-center">
          <p className="font-mono text-sm text-text-dim">
            1. Index your website · 2. Refresh Market Depth · 3. Run Fit Analysis
          </p>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <div className="bg-panel border border-border rounded-lg p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <span className={`font-mono text-xs font-bold ${VERDICT_COLORS[selected.verdict].text}`}>
                {selected.verdict}
              </span>
              <h3 className="font-display text-xl font-semibold mt-1">{selected.domain_name}</h3>
              <p className="font-mono text-[10px] text-text-dim mt-1">
                can build: {selected.verdict_detail?.can_build ? "yes" : "needs gaps closed"} ·
                confidence: {selected.verdict_detail?.confidence || "—"}
              </p>
            </div>
            <button onClick={() => setSelected(null)} className="font-mono text-xs text-text-dim">Close</button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-4">
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Market Need</h4>
                <p className="text-sm text-text-secondary leading-relaxed">{selected.verdict_detail?.market_need}</p>
              </section>
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Your Strengths</h4>
                <ul className="text-sm text-text-secondary space-y-1">
                  {(selected.verdict_detail?.our_strengths || []).map((s, i) => (
                    <li key={i} className="flex gap-2"><span className="text-ok">✓</span>{s}</li>
                  ))}
                </ul>
              </section>
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Gaps to Close</h4>
                <ul className="text-sm text-text-secondary space-y-1">
                  {(selected.verdict_detail?.gaps || []).map((g, i) => (
                    <li key={i} className="flex gap-2"><span className="text-yellow-500">!</span>{g}</li>
                  ))}
                </ul>
              </section>
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Depth Assessment</h4>
                <p className="text-sm text-text-secondary">{selected.verdict_detail?.depth_assessment}</p>
              </section>
            </div>

            <div className="space-y-4">
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">How to Build</h4>
                <div className="space-y-2 text-sm text-text-secondary">
                  {selected.verdict_detail?.how_to_build?.phase_1 && (
                    <p><b className="text-text-primary">Phase 1:</b> {selected.verdict_detail.how_to_build.phase_1}</p>
                  )}
                  {selected.verdict_detail?.how_to_build?.phase_2 && (
                    <p><b className="text-text-primary">Phase 2:</b> {selected.verdict_detail.how_to_build.phase_2}</p>
                  )}
                  {selected.verdict_detail?.how_to_build?.phase_3 && (
                    <p><b className="text-text-primary">Phase 3:</b> {selected.verdict_detail.how_to_build.phase_3}</p>
                  )}
                </div>
              </section>
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Revenue Path</h4>
                <p className="text-sm text-text-secondary">{selected.verdict_detail?.revenue_path}</p>
              </section>
              <section>
                <h4 className="font-mono text-[10px] text-text-dim uppercase mb-2">Evidence (RAG citations)</h4>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {selected.citations.map((c, i) => (
                    <div key={i} className="border border-border rounded p-2 text-xs">
                      <div className="flex justify-between gap-2">
                        <span className="font-mono text-accent-b truncate">{c.title || c.url}</span>
                        <span className="font-mono text-[9px] text-text-dim shrink-0">{c.source_type}</span>
                      </div>
                      <p className="text-text-dim mt-1 line-clamp-3">{c.excerpt}</p>
                      {c.url && (
                        <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[10px] text-accent-a mt-1 inline-block">
                          source →
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
