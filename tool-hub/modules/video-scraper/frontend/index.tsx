"use client";

import { useCallback, useEffect, useState } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";

type Job = {
  id: string;
  source_url: string;
  source_type?: string;
  status: string;
  error?: string;
  title?: string;
  channel_or_author?: string;
  duration_seconds?: number;
  thumbnail_url?: string;
  transcript?: string;
  transcript_source?: string;
  summary_json?: {
    one_line_summary: string;
    key_points: string[];
    chapters: { timestamp_hint: string; title: string }[];
    notable_quotes: string[];
    topics: string[];
  };
  created_at?: string;
};

const STAGES = ["queued", "extracting", "transcribing", "summarizing", "done"];

function StageStepper({ status }: { status: string }) {
  const idx = STAGES.indexOf(status);
  const activeIdx = idx === -1 ? (status === "failed" ? -1 : 0) : idx;

  return (
    <div className="flex items-center gap-1 mb-6 overflow-x-auto">
      {STAGES.slice(1).map((stage, i) => {
        const stageIdx = i + 1;
        const done = activeIdx >= stageIdx;
        const current = activeIdx === stageIdx;
        return (
          <div key={stage} className="flex items-center gap-1">
            <div
              className={`font-mono text-[10px] px-2 py-1 rounded uppercase tracking-wider whitespace-nowrap ${
                done
                  ? "bg-ok/15 text-ok border border-ok/30"
                  : current
                  ? "bg-accent-a/15 text-accent-a border border-accent-a/30 animate-pulse"
                  : "bg-panel text-text-dim border border-border"
              }`}
            >
              {stage}
            </div>
            {i < STAGES.length - 2 && (
              <span className="text-text-dim text-xs">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function VideoScraperPanel() {
  const { backendUrl } = useToolContext();
  const apiBase =
    typeof window !== "undefined"
      ? backendUrl.replace("video-scraper-api", "localhost")
      : backendUrl;

  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<"overview" | "summary" | "transcript" | "export">("overview");
  const [loading, setLoading] = useState(false);

  const fetchRecent = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/jobs?limit=10`);
      const data = await res.json();
      setRecentJobs(data.jobs || []);
    } catch {
      /* ignore */
    }
  }, [apiBase]);

  useEffect(() => {
    fetchRecent();
  }, [fetchRecent]);

  useEffect(() => {
    if (!activeJob || ["done", "failed"].includes(activeJob.status)) return;
    const interval = setInterval(async () => {
      const res = await fetch(`${apiBase}/jobs/${activeJob.id}`);
      const job = await res.json();
      setActiveJob(job);
      if (job.status === "done" || job.status === "failed") {
        fetchRecent();
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [activeJob, apiBase, fetchRecent]);

  const handleScrape = async () => {
    try {
      new URL(url);
    } catch {
      setUrlError("Enter a valid URL");
      return;
    }
    setUrlError("");
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      const jobRes = await fetch(`${apiBase}/jobs/${data.job_id}`);
      setActiveJob(await jobRes.json());
    } catch (e) {
      setUrlError("Failed to start scrape");
    } finally {
      setLoading(false);
    }
  };

  const copyTranscript = () => {
    if (activeJob?.transcript) navigator.clipboard.writeText(activeJob.transcript);
  };

  const downloadExport = (format: "md" | "json") => {
    if (!activeJob) return;
    const content =
      format === "json"
        ? JSON.stringify(activeJob, null, 2)
        : `# ${activeJob.title}\n\n${activeJob.summary_json?.one_line_summary}\n\n## Key Points\n${activeJob.summary_json?.key_points.map((p) => `- ${p}`).join("\n")}\n\n## Transcript\n${activeJob.transcript}`;
    const blob = new Blob([content], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `scrape-${activeJob.id}.${format === "json" ? "json" : "md"}`;
    a.click();
  };

  const isRunning = activeJob && !["done", "failed"].includes(activeJob.status);

  return (
    <div className="flex gap-6">
      <div className="flex-1 min-w-0">
        <div className="sticky top-14 z-40 bg-bg/90 backdrop-blur py-4 border-b border-border mb-6">
          <div className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste any video URL — YouTube, embedded player, direct .mp4…"
              className="flex-1 bg-panel border border-border rounded-lg px-4 py-2.5 font-mono text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-accent-a"
            />
            <button
              onClick={handleScrape}
              disabled={loading || !url}
              className="font-mono text-sm bg-accent-a text-bg px-5 py-2.5 rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              {loading ? "Starting…" : "Scrape"}
            </button>
          </div>
          {urlError && (
            <p className="text-red-400 font-mono text-xs mt-2">{urlError}</p>
          )}
        </div>

        {!activeJob && (
          <div className="text-center py-20 border border-dashed border-border rounded-lg">
            <p className="font-display text-lg text-text-secondary mb-2">
              No scrape in progress
            </p>
            <p className="font-mono text-xs text-text-dim">
              Paste a URL above to extract transcript + summary
            </p>
          </div>
        )}

        {activeJob && isRunning && (
          <div className="bg-panel border border-border rounded-lg p-6">
            <p className="font-mono text-xs text-text-dim mb-4">PIPELINE</p>
            <StageStepper status={activeJob.status} />
            <p className="font-mono text-sm text-text-secondary animate-pulse">
              Processing {activeJob.source_url}…
            </p>
          </div>
        )}

        {activeJob?.status === "failed" && (
          <div className="bg-red-950/30 border border-red-800 rounded-lg p-6">
            <p className="font-mono text-sm text-red-400">Scrape failed</p>
            <p className="font-mono text-xs text-red-300/80 mt-2">{activeJob.error}</p>
          </div>
        )}

        {activeJob?.status === "done" && (
          <div>
            <div className="flex gap-1 mb-4 border-b border-border">
              {(["overview", "summary", "transcript", "export"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`font-mono text-xs px-4 py-2 capitalize border-b-2 -mb-px transition-colors ${
                    tab === t
                      ? "border-accent-a text-accent-a"
                      : "border-transparent text-text-dim hover:text-text-secondary"
                  }`}
                >
                  {t === "export" ? "Raw / Export" : t}
                </button>
              ))}
            </div>

            {tab === "overview" && (
              <div className="bg-panel border border-border rounded-lg p-6">
                <div className="flex gap-4 mb-4">
                  {activeJob.thumbnail_url && (
                    <img
                      src={activeJob.thumbnail_url}
                      alt=""
                      className="w-40 rounded border border-border"
                    />
                  )}
                  <div>
                    <h2 className="font-display text-xl font-semibold">{activeJob.title}</h2>
                    <p className="font-mono text-xs text-text-dim mt-1">
                      {activeJob.channel_or_author}
                      {activeJob.duration_seconds
                        ? ` · ${Math.floor(activeJob.duration_seconds / 60)}m`
                        : ""}
                    </p>
                    <p className="text-text-secondary mt-3 leading-relaxed">
                      {activeJob.summary_json?.one_line_summary}
                    </p>
                    <div className="flex gap-1.5 mt-3 flex-wrap">
                      {activeJob.summary_json?.topics.map((t) => (
                        <span
                          key={t}
                          className="font-mono text-[10px] bg-accent-a/10 text-accent-a border border-accent-a/30 px-2 py-0.5 rounded"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {tab === "summary" && (
              <div className="bg-panel border border-border rounded-lg p-6 space-y-6">
                <div>
                  <h3 className="font-mono text-xs text-text-dim uppercase mb-3">Key Points</h3>
                  <ul className="space-y-2">
                    {activeJob.summary_json?.key_points.map((p, i) => (
                      <li key={i} className="text-text-secondary text-sm leading-relaxed pl-4 border-l-2 border-accent-a/40">
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="font-mono text-xs text-text-dim uppercase mb-3">Chapters</h3>
                  <div className="space-y-2">
                    {activeJob.summary_json?.chapters.map((c, i) => (
                      <div key={i} className="flex gap-3 font-mono text-sm">
                        <span className="text-accent-a shrink-0">{c.timestamp_hint}</span>
                        <span className="text-text-secondary">{c.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {activeJob.summary_json?.notable_quotes?.length ? (
                  <div>
                    <h3 className="font-mono text-xs text-text-dim uppercase mb-3">Quotes</h3>
                    {activeJob.summary_json.notable_quotes.map((q, i) => (
                      <blockquote
                        key={i}
                        className="border-l-2 border-accent-b pl-4 text-text-secondary italic mb-3"
                      >
                        {q}
                      </blockquote>
                    ))}
                  </div>
                ) : null}
              </div>
            )}

            {tab === "transcript" && (
              <div className="bg-panel border border-border rounded-lg p-6">
                <div className="flex justify-between items-center mb-4">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-text-dim border border-border px-2 py-0.5 rounded">
                    {activeJob.transcript_source}
                  </span>
                  <button
                    onClick={copyTranscript}
                    className="font-mono text-xs border border-border-bright px-3 py-1 rounded hover:border-text-primary"
                  >
                    Copy
                  </button>
                </div>
                <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap max-h-[500px] overflow-y-auto leading-relaxed">
                  {activeJob.transcript}
                </pre>
              </div>
            )}

            {tab === "export" && (
              <div className="bg-panel border border-border rounded-lg p-6 flex gap-3">
                <button
                  onClick={() => downloadExport("md")}
                  className="font-mono text-xs bg-panel-raised border border-border px-4 py-2 rounded hover:border-accent-a"
                >
                  Download .md
                </button>
                <button
                  onClick={() => downloadExport("json")}
                  className="font-mono text-xs bg-panel-raised border border-border px-4 py-2 rounded hover:border-accent-a"
                >
                  Download .json
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <aside className="w-64 shrink-0 hidden lg:block">
        <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-3">
          Recent Scrapes
        </h3>
        <div className="space-y-2">
          {recentJobs.map((job) => (
            <button
              key={job.id}
              onClick={() => setActiveJob(job)}
              className="w-full text-left bg-panel border border-border rounded-lg p-3 hover:border-border-bright transition-colors"
            >
              <p className="font-mono text-xs text-text-primary truncate">
                {job.title || job.source_url}
              </p>
              <p className="font-mono text-[10px] text-text-dim mt-1">{job.status}</p>
            </button>
          ))}
          {recentJobs.length === 0 && (
            <p className="font-mono text-xs text-text-dim">No history yet</p>
          )}
        </div>
      </aside>
    </div>
  );
}
