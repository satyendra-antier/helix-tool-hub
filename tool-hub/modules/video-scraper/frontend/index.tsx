"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  Input,
  Progress as ProgressBarUI,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useToast,
} from "@tool-hub/ui";
import { buildScrapePdf } from "./pdf-export";

const ACTIVE_JOB_KEY = "toolhub.videoScraper.activeJobId";
const TERMINAL_STATUSES = new Set(["done", "partial", "failed"]);

type Progress = {
  videos_total?: number;
  videos_done?: number;
  videos_failed?: number;
  videos_processing?: number;
  percent?: number;
  current_index?: number;
  current_video_title?: string;
  current_status?: string;
};

type VideoItem = {
  id: string;
  video_url: string;
  sort_order: number;
  status: string;
  error?: string;
  title?: string;
  channel_or_author?: string;
  duration_seconds?: number;
  thumbnail_url?: string;
  transcript?: string;
  transcript_source?: string;
  summary_json?: SummaryJson;
};

type SummaryJson = {
  one_line_summary: string;
  key_points: string[];
  chapters: { timestamp_hint: string; title: string }[];
  notable_quotes: string[];
  topics: string[];
};

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
  summary_json?: SummaryJson;
  is_batch?: boolean;
  progress?: Progress;
  items?: VideoItem[];
  items_count?: number;
  created_at?: string;
  completed_at?: string;
};

type ViewTarget = {
  id: string;
  title?: string;
  channel_or_author?: string;
  duration_seconds?: number;
  thumbnail_url?: string;
  transcript?: string;
  transcript_source?: string;
  summary_json?: SummaryJson;
  video_url?: string;
  status: string;
  error?: string;
};

function ProgressBar({ progress }: { progress?: Progress }) {
  const pct = Math.min(100, Math.max(0, progress?.percent ?? 0));
  const total = progress?.videos_total ?? 0;
  const done = progress?.videos_done ?? 0;
  const failed = progress?.videos_failed ?? 0;

  return (
    <div className="mb-4 space-y-2">
      <div className="flex justify-between text-xs text-text-secondary">
        <span>{total > 1 ? `Video ${done + failed} of ${total}` : "Processing video"}</span>
        <span className="text-primary font-medium">{pct}%</span>
      </div>
      <ProgressBarUI value={pct} />
      {failed > 0 && <p className="text-xs text-danger">{failed} failed</p>}
      {progress?.current_video_title && progress.current_status && (
        <p className="text-xs text-text-muted truncate">
          {progress.current_status}: {progress.current_video_title}
        </p>
      )}
    </div>
  );
}

function itemStatusIcon(status: string) {
  if (status === "done") return <span className="text-ok">✓</span>;
  if (status === "failed") return <span className="text-red-400">✗</span>;
  if (status === "queued") return <span className="text-text-dim">○</span>;
  return <span className="text-accent-a animate-pulse">●</span>;
}

export default function VideoScraperPanel() {
  const { backendUrl } = useToolContext();
  const apiBase = backendUrl;
  const { toast } = useToast();

  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<"overview" | "summary" | "transcript" | "export">("overview");
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [showCompleteBanner, setShowCompleteBanner] = useState(false);
  const prevStatusRef = useRef<string | null>(null);

  const fetchJob = useCallback(async (jobId: string) => {
    const res = await fetch(`${apiBase}/jobs/${jobId}`);
    if (!res.ok) throw new Error("Job not found");
    return (await res.json()) as Job;
  }, [apiBase]);

  const fetchRecent = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/jobs?limit=10`);
      const data = await res.json();
      setRecentJobs(data.jobs || []);
    } catch {
      /* ignore */
    }
  }, [apiBase]);

  const persistActiveJob = (jobId: string | null) => {
    if (typeof window === "undefined") return;
    if (jobId) localStorage.setItem(ACTIVE_JOB_KEY, jobId);
    else localStorage.removeItem(ACTIVE_JOB_KEY);
  };

  useEffect(() => {
    let cancelled = false;

    const applyJob = (job: Job) => {
      setActiveJob(job);
      if (job.is_batch && job.items?.length) {
        const firstDone = job.items.find((i) => i.status === "done");
        setSelectedItemId(firstDone?.id ?? job.items[0].id);
      }
      if (TERMINAL_STATUSES.has(job.status)) persistActiveJob(null);
      else persistActiveJob(job.id);
    };

    (async () => {
      setRestoring(true);
      try {
        let recent: Job[] = [];
        try {
          const res = await fetch(`${apiBase}/jobs?limit=10`);
          const data = await res.json();
          recent = data.jobs || [];
          if (!cancelled) setRecentJobs(recent);
        } catch {
          /* ignore list errors */
        }

        const saved = typeof window !== "undefined" ? localStorage.getItem(ACTIVE_JOB_KEY) : null;
        let restored: Job | null = null;

        if (saved) {
          try {
            restored = await fetchJob(saved);
          } catch {
            /* keep key; fall through to recent running job */
          }
        }

        if (!restored) {
          const running = recent.find((j) => !TERMINAL_STATUSES.has(j.status));
          if (running) {
            try {
              restored = await fetchJob(running.id);
            } catch {
              /* ignore */
            }
          }
        }

        if (!cancelled && restored) applyJob(restored);
        else if (saved && !restored) {
          const listed = recent.some((j) => j.id === saved && !TERMINAL_STATUSES.has(j.status));
          if (!listed) persistActiveJob(null);
        }
      } finally {
        if (!cancelled) setRestoring(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiBase, fetchJob]);

  useEffect(() => {
    if (!activeJob || TERMINAL_STATUSES.has(activeJob.status)) return;
    const interval = setInterval(async () => {
      try {
        const job = await fetchJob(activeJob.id);
        setActiveJob(job);
        if (TERMINAL_STATUSES.has(job.status)) {
          persistActiveJob(null);
          fetchRecent();
          clearInterval(interval);
        }
      } catch {
        clearInterval(interval);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [activeJob?.id, activeJob?.status, fetchJob, fetchRecent]);

  // As soon as any batch item finishes, surface it without waiting for the whole job.
  useEffect(() => {
    if (!activeJob?.is_batch || !activeJob.items?.length) return;
    if (selectedItemId) {
      const stillThere = activeJob.items.some((i) => i.id === selectedItemId);
      if (stillThere) return;
    }
    const firstDone = activeJob.items.find((i) => i.status === "done");
    if (firstDone) {
      setSelectedItemId(firstDone.id);
      setTab("overview");
    }
  }, [activeJob?.id, activeJob?.is_batch, activeJob?.items, selectedItemId]);

  useEffect(() => {
    if (!activeJob) return;
    const prev = prevStatusRef.current;
    prevStatusRef.current = activeJob.status;
    if (
      prev &&
      !TERMINAL_STATUSES.has(prev) &&
      (activeJob.status === "done" || activeJob.status === "partial")
    ) {
      setShowCompleteBanner(true);
      const t = setTimeout(() => setShowCompleteBanner(false), 8000);
      return () => clearTimeout(t);
    }
  }, [activeJob?.status]);

  const handleScrape = async () => {
    try {
      new URL(url);
    } catch {
      setUrlError("Enter a valid URL");
      return;
    }
    setUrlError("");
    setLoading(true);
    setShowCompleteBanner(false);
    try {
      const res = await fetch(`${apiBase}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      const job = await fetchJob(data.job_id);
      setActiveJob(job);
      setSelectedItemId(null);
      persistActiveJob(data.job_id);
      prevStatusRef.current = job.status;
    } catch {
      setUrlError("Failed to start scrape");
    } finally {
      setLoading(false);
    }
  };

  const selectJob = async (job: Job) => {
    const full = await fetchJob(job.id);
    setActiveJob(full);
    setTab("overview");
    if (full.is_batch && full.items?.length) {
      const firstDone = full.items.find((i) => i.status === "done");
      setSelectedItemId(firstDone?.id ?? full.items[0].id);
    } else {
      setSelectedItemId(null);
    }
    if (!TERMINAL_STATUSES.has(full.status)) persistActiveJob(full.id);
    else persistActiveJob(null);
  };

  const viewTarget: ViewTarget | null = (() => {
    if (!activeJob) return null;
    if (activeJob.is_batch && activeJob.items?.length) {
      const item = activeJob.items.find((i) => i.id === selectedItemId) ?? activeJob.items[0];
      return {
        id: item.id,
        title: item.title,
        channel_or_author: item.channel_or_author,
        duration_seconds: item.duration_seconds,
        thumbnail_url: item.thumbnail_url,
        transcript: item.transcript,
        transcript_source: item.transcript_source,
        summary_json: item.summary_json,
        video_url: item.video_url,
        status: item.status,
        error: item.error,
      };
    }
    return {
      id: activeJob.id,
      title: activeJob.title,
      channel_or_author: activeJob.channel_or_author,
      duration_seconds: activeJob.duration_seconds,
      thumbnail_url: activeJob.thumbnail_url,
      transcript: activeJob.transcript,
      transcript_source: activeJob.transcript_source,
      summary_json: activeJob.summary_json,
      video_url: activeJob.source_url,
      status: activeJob.status,
      error: activeJob.error,
    };
  })();

  const copyTranscript = () => {
    if (viewTarget?.transcript) {
      navigator.clipboard.writeText(viewTarget.transcript);
      toast("Transcript copied", "success");
    }
  };

  const downloadExport = (format: "md" | "json" | "pdf") => {
    if (!viewTarget || !activeJob) return;
    const payload = activeJob.is_batch
      ? { job: activeJob, item: viewTarget }
      : activeJob;

    let blob: Blob;
    let ext: string;
    if (format === "pdf") {
      blob = buildScrapePdf({
        title: viewTarget.title || "Video Scrape",
        channel: viewTarget.channel_or_author,
        durationSeconds: viewTarget.duration_seconds,
        oneLineSummary: viewTarget.summary_json?.one_line_summary,
        keyPoints: viewTarget.summary_json?.key_points,
        chapters: viewTarget.summary_json?.chapters,
        topics: viewTarget.summary_json?.topics,
        transcript: viewTarget.transcript,
        sourceUrl: viewTarget.video_url || activeJob.source_url,
      });
      ext = "pdf";
    } else if (format === "json") {
      blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      ext = "json";
    } else {
      const content = `# ${viewTarget.title}\n\n${viewTarget.summary_json?.one_line_summary}\n\n## Key Points\n${viewTarget.summary_json?.key_points?.map((p) => `- ${p}`).join("\n") ?? ""}\n\n## Transcript\n${viewTarget.transcript ?? ""}`;
      blob = new Blob([content], { type: "text/markdown" });
      ext = "md";
    }

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `scrape-${viewTarget.id}.${ext}`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const isRunning = activeJob && !TERMINAL_STATUSES.has(activeJob.status);
  const isComplete = activeJob && (activeJob.status === "done" || activeJob.status === "partial");
  const doneItemsCount = activeJob?.items?.filter((i) => i.status === "done").length ?? 0;
  // Show per-video results as soon as any item is done, not only when the batch finishes.
  const showResults =
    !!isComplete ||
    (!!isRunning && !!activeJob?.is_batch && (doneItemsCount > 0 || (activeJob.items?.length ?? 0) > 0));
  const canViewContent = viewTarget?.status === "done";

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-text-secondary mb-3">
          Pages with multiple videos are scraped one-by-one (up to 25 per page). Progress survives page refresh.
        </p>

        {showCompleteBanner && activeJob && (
          <Alert variant="success" title="Scrape complete" className="mb-4">
            {activeJob.progress?.videos_done ?? 0} video(s) processed
            {(activeJob.progress?.videos_failed ?? 0) > 0 ? ` · ${activeJob.progress?.videos_failed} failed` : ""}
          </Alert>
        )}

        <Card className="mb-6 accent-strip">
          <CardContent className="py-4">
            <div className="flex gap-2">
              <Input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Paste a page URL or single video link…"
                className="flex-1"
              />
              <Button onClick={handleScrape} disabled={loading || !!isRunning || !url}>
                {loading ? "Starting…" : isRunning ? "Running…" : "Scrape"}
              </Button>
            </div>
            {urlError && <p className="text-danger text-xs mt-2">{urlError}</p>}
          </CardContent>
        </Card>

        {restoring && !activeJob && (
          <p className="text-sm text-text-secondary mb-6">Restoring scrape progress…</p>
        )}

        {!restoring && !activeJob && (
          <EmptyState
            title="No scrape in progress"
            description="Paste a URL above to extract transcripts and summaries."
          />
        )}

        {activeJob && isRunning && (
          <Card className="mb-6">
            <CardContent className="py-5">
            <div className="flex items-center gap-2 mb-4">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-a opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-a" />
              </span>
              <p className="font-mono text-xs text-accent-a uppercase tracking-wider">
                {activeJob.status === "discovering"
                  ? "Discovering videos…"
                  : doneItemsCount > 0
                    ? `Processing… ${doneItemsCount} ready to view`
                    : "Processing batch…"}
              </p>
            </div>
            <ProgressBar progress={activeJob.progress} />
            <p className="font-mono text-sm text-text-secondary truncate">{activeJob.source_url}</p>
            {doneItemsCount > 0 && (
              <p className="text-xs text-ok mt-3">
                Completed videos are available below — you can open them while others finish.
              </p>
            )}
            </CardContent>
          </Card>
        )}

        {activeJob?.status === "failed" && !activeJob.is_batch && (
          <Alert variant="danger" title="Scrape failed">{activeJob.error}</Alert>
        )}

        {showResults && activeJob && (
          <div>
            {activeJob.is_batch && activeJob.items && (
              <div className="mb-4">
                <h3 className="font-mono text-xs text-text-dim uppercase mb-2">
                  Videos ({activeJob.progress?.videos_done}/{activeJob.progress?.videos_total})
                </h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  {activeJob.items.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => {
                        setSelectedItemId(item.id);
                        setTab("overview");
                      }}
                      className={`text-left border rounded-lg p-3 transition-colors ${
                        selectedItemId === item.id
                          ? "border-accent-a bg-accent-a/5"
                          : item.status === "done"
                            ? "border-border bg-panel hover:border-border-bright"
                            : "border-border bg-surface-muted/50 hover:border-border-bright opacity-80"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <span className="mt-0.5">{itemStatusIcon(item.status)}</span>
                        <div className="min-w-0">
                          <p className="font-mono text-xs text-text-primary truncate">
                            {item.title || `Video ${item.sort_order + 1}`}
                          </p>
                          <p className="font-mono text-[10px] text-text-dim mt-0.5">
                            {item.status === "done" ? "Ready · click to view" : item.status}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeJob.status === "partial" && (
              <p className="font-mono text-xs text-amber-700 mb-4">{activeJob.error}</p>
            )}

            {canViewContent && viewTarget && (
              <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
                <TabsList>
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="summary">Summary</TabsTrigger>
                  <TabsTrigger value="transcript">Transcript</TabsTrigger>
                  <TabsTrigger value="export">Export</TabsTrigger>
                </TabsList>

                <TabsContent value="overview">
                  <Card>
                    <CardContent className="py-5">
                    <div className="flex gap-4 mb-4">
                      {viewTarget.thumbnail_url && (
                        <img
                          src={viewTarget.thumbnail_url}
                          alt={viewTarget.title || "Video thumbnail"}
                          className="w-40 rounded-lg border border-border"
                        />
                      )}
                      <div>
                        <h2 className="font-display text-xl font-semibold">{viewTarget.title}</h2>
                        <p className="font-mono text-xs text-text-dim mt-1">
                          {viewTarget.channel_or_author}
                          {viewTarget.duration_seconds
                            ? ` · ${Math.floor(viewTarget.duration_seconds / 60)}m`
                            : ""}
                        </p>
                        <p className="text-text-secondary mt-3 leading-relaxed">
                          {viewTarget.summary_json?.one_line_summary}
                        </p>
                        <div className="flex gap-1.5 mt-3 flex-wrap">
                          {viewTarget.summary_json?.topics?.map((t) => (
                            <Badge key={t} variant="primary">{t}</Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="summary">
                  <Card>
                    <CardContent className="py-5 space-y-6">
                    <div>
                      <h3 className="font-mono text-xs text-text-dim uppercase mb-3">Key Points</h3>
                      <ul className="space-y-2">
                        {viewTarget.summary_json?.key_points?.map((p, i) => (
                          <li
                            key={i}
                            className="text-text-secondary text-sm leading-relaxed pl-4 border-l-2 border-accent-a/40"
                          >
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className="font-mono text-xs text-text-dim uppercase mb-3">Chapters</h3>
                      <div className="space-y-2">
                        {viewTarget.summary_json?.chapters?.map((c, i) => (
                          <div key={i} className="flex gap-3 font-mono text-sm">
                            <span className="text-accent-a shrink-0">{c.timestamp_hint}</span>
                            <span className="text-text-secondary">{c.title}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="transcript">
                  <Card>
                    <CardContent className="py-5">
                    <div className="flex justify-between items-center mb-4">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-text-dim border border-border px-2 py-0.5 rounded">
                        {viewTarget.transcript_source}
                      </span>
                      <Button variant="outline" size="sm" onClick={copyTranscript}>Copy</Button>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap max-h-[500px] overflow-y-auto leading-relaxed">
                      {viewTarget.transcript}
                    </pre>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="export">
                  <Card>
                    <CardContent className="py-5 flex gap-3">
                      <Button variant="outline" onClick={() => downloadExport("md")}>Download .md</Button>
                      <Button variant="outline" onClick={() => downloadExport("pdf")}>Download .pdf</Button>
                      <Button variant="outline" onClick={() => downloadExport("json")}>Download .json</Button>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            )}

            {viewTarget && viewTarget.status !== "done" && viewTarget.status !== "failed" && (
              <p className="text-sm text-text-secondary mt-2">
                This video is still processing ({viewTarget.status})… results will appear here when ready.
              </p>
            )}

            {viewTarget && viewTarget.status === "failed" && (
              <Alert variant="danger" title="This video failed" className="mt-2">
                {viewTarget.error}
              </Alert>
            )}
          </div>
        )}
      </div>

      <aside className="w-full lg:w-64 shrink-0">
        <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">Recent scrapes</h3>
        <div className="space-y-2">
          {recentJobs.map((job) => (
            <button
              key={job.id}
              onClick={() => selectJob(job)}
              className={`w-full text-left bg-panel border rounded-lg p-3 transition-colors ${
                activeJob?.id === job.id ? "border-accent-a" : "border-border hover:border-border-bright"
              }`}
            >
              <p className="font-mono text-xs text-text-primary truncate">
                {job.title || job.source_url}
              </p>
              <p className="font-mono text-[10px] text-text-dim mt-1">
                {job.status}
                {job.is_batch && job.progress?.videos_total
                  ? ` · ${job.progress.videos_done}/${job.progress.videos_total}`
                  : ""}
              </p>
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}
