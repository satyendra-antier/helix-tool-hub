"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  Input,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  useToast,
} from "@tool-hub/ui";

type Status = {
  autopilot_enabled: boolean;
  paused: boolean;
  approve_first_message: boolean;
  mailboxes: number;
  mailboxes_active: number;
  sandbox_only: boolean;
  waiting_approval: number;
  in_sequence: number;
  hot_leads: number;
  sent_today: number;
  replies_today: number;
  unread_replies: number;
  in_send_window: boolean;
  last_heartbeat?: string | null;
  next_heartbeat?: string | null;
};

type Enrollment = {
  id: string;
  lead_id: string;
  lead_name?: string;
  company_domain?: string;
  contact_email: string;
  contact_name?: string;
  contact_title?: string;
  phone?: string | null;
  current_step: number;
  status: string;
  next_action_at?: string | null;
  subject?: string | null;
  last_sent_at?: string | null;
  lead_score?: number | null;
  fit_reason?: string | null;
  call_status?: string | null;
};

type Msg = {
  id: string;
  enrollment_id: string;
  step: number;
  kind: string;
  status: string;
  subject?: string;
  body?: string;
  sent_at?: string | null;
  error?: string | null;
  created_at?: string;
};

type QueueItem = Msg & { enrollment: Enrollment };

type ReplyRow = {
  id: string;
  enrollment_id?: string | null;
  from_email?: string;
  subject?: string;
  body?: string;
  category?: string;
  category_label?: string;
  reasoning?: string;
  action_taken?: string;
  handled: boolean;
  received_at?: string;
  lead_name?: string;
  contact_name?: string;
};

type CallRow = {
  id: string;
  enrollment_id: string;
  phone: string;
  status: string;
  outcome?: string | null;
  summary?: string | null;
  error?: string | null;
  created_at?: string;
  lead_name?: string;
  contact_name?: string;
};

type Thread = Enrollment & {
  messages: Msg[];
  replies: ReplyRow[];
  calls: CallRow[];
  steps: { step: number; kind: string; label: string; wait_days: number }[];
};

type Mailbox = {
  id: string;
  label: string;
  email: string;
  from_name?: string;
  kind: string;
  smtp_host?: string;
  imap_host?: string;
  has_password: boolean;
  daily_cap_today: number;
  daily_cap_max: number;
  active: boolean;
  paused_reason?: string | null;
  sent_today: number;
  sent_total: number;
  bounce_rate: number;
  last_error?: string | null;
};

type Settings = Record<string, unknown>;
type Sequence = { id: string; name: string; steps: { step: number; kind: string; label: string; wait_days: number }[] };

type EventRow = { id: string; kind: string; text: string; detail: Record<string, unknown>; lead_name?: string; contact?: string; created_at?: string };

type Report = {
  totals: Record<string, number>;
  by_step: { step: number; sent: number; replies: number; positive: number; reply_rate: number }[];
  by_subject: { subject: string; sent: number; replies: number; positive: number; reply_rate: number }[];
  reply_types: Record<string, number>;
  learnings: string[];
};

type Config = {
  openai_configured: boolean;
  alerts: Record<string, boolean>;
  crm: Record<string, boolean>;
  calls_configured: boolean;
  calls_webhook_url: string;
  heartbeat_minutes: number;
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_approval: "Waiting for approval",
  active: "In sequence",
  snoozed: "Snoozed",
  replied: "Replied",
  interested: "Interested",
  completed: "Finished, no reply",
  stopped: "Stopped",
  bounced: "Bounced",
  unsubscribed: "Unsubscribed",
};

const STATUS_VARIANT: Record<string, "default" | "primary" | "success" | "warning" | "danger" | "muted"> = {
  awaiting_approval: "warning",
  active: "primary",
  snoozed: "muted",
  replied: "success",
  interested: "success",
  completed: "muted",
  stopped: "muted",
  bounced: "danger",
  unsubscribed: "danger",
};

const CATEGORY_VARIANT: Record<string, "default" | "primary" | "success" | "warning" | "danger" | "muted"> = {
  interested: "success",
  question: "primary",
  not_now: "warning",
  not_interested: "muted",
  unsubscribe: "danger",
  out_of_office: "muted",
  referral: "primary",
};

const KIND_LABEL: Record<string, string> = {
  opener: "First email",
  follow_up: "Follow-up",
  insight: "Useful idea",
  soft_close: "Last note",
  answer: "Answer to reply",
};

const SAMPLE_REPLIES: { label: string; text: string }[] = [
  { label: "Interested", text: "Sounds interesting, happy to chat next week. What does your process look like?" },
  { label: "Question", text: "What would something like this cost roughly?" },
  { label: "Not now", text: "Not right now, maybe next quarter." },
  { label: "Not interested", text: "No thanks, we already have a vendor." },
  { label: "Out of office", text: "Automatic reply: I am out of office until next Monday with limited access to email." },
  { label: "Referral", text: "I'm not the right person, please reach out to partnerships@example.com." },
  { label: "Unsubscribe", text: "Please remove me from your list." },
];

function when(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (d.getTime() - Date.now()) / 60000;
  const abs = Math.abs(diff);
  const txt = abs < 60 ? `${Math.round(abs)} min` : abs < 1440 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} d`;
  return diff >= 0 ? `in ${txt}` : `${txt} ago`;
}

function pct(n?: number) {
  return `${Math.round((n || 0) * 100)}%`;
}

export default function ReachOutPanel() {
  const { backendUrl } = useToolContext();
  const { toast } = useToast();

  const [tab, setTab] = useState("today");
  const [status, setStatus] = useState<Status | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [edits, setEdits] = useState<Record<string, { subject: string; body: string }>>({});
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [statusFilter, setStatusFilter] = useState("active,awaiting_approval,snoozed,replied,interested");
  const [inbox, setInbox] = useState<ReplyRow[]>([]);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [today, setToday] = useState<{ due_next_24h: Enrollment[]; hot_replies: ReplyRow[]; drafted_today: number } | null>(null);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [settings, setSettings] = useState<Settings>({});
  const [sequence, setSequence] = useState<Sequence | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newBox, setNewBox] = useState({ email: "", password: "", from_name: "", smtp_host: "", imap_host: "" });
  const [simText, setSimText] = useState("");
  const [phone, setPhone] = useState("");

  const api = useCallback(
    async (path: string, init?: RequestInit & { json?: unknown }) => {
      const res = await fetch(`${backendUrl}${path}`, {
        ...init,
        headers: init?.json !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((data as { detail?: string }).detail || `Request failed (${res.status})`);
      return data;
    },
    [backendUrl]
  );

  const loadStatus = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([api("/status"), api("/config")]);
      setStatus(s);
      setConfig(c);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, [api]);

  const loadTab = useCallback(async () => {
    try {
      if (tab === "today") {
        const [t, ev] = await Promise.all([api("/today"), api("/events?limit=40")]);
        setToday(t);
        setEvents(ev.events);
      } else if (tab === "queue") {
        const q = await api("/queue");
        setQueue(q.items);
        setEdits(Object.fromEntries(q.items.map((i: QueueItem) => [i.id, { subject: i.subject || "", body: i.body || "" }])));
      } else if (tab === "sequences") {
        const e = await api(`/enrollments?status=${statusFilter}`);
        setEnrollments(e.enrollments);
      } else if (tab === "inbox") {
        setInbox((await api("/inbox")).replies);
      } else if (tab === "calls") {
        setCalls((await api("/calls")).calls);
      } else if (tab === "results") {
        setReport(await api("/reports/summary?days=30"));
      } else if (tab === "setup") {
        const [m, s, seq] = await Promise.all([api("/mailboxes"), api("/settings"), api("/sequences")]);
        setMailboxes(m.mailboxes);
        setSettings(s);
        setSequence(seq.sequences.find((x: Sequence & { is_default: boolean }) => x.is_default) || seq.sequences[0] || null);
      }
    } catch (e) {
      toast((e as Error).message);
    }
  }, [api, tab, statusFilter, toast]);

  useEffect(() => {
    loadStatus();
    const t = setInterval(loadStatus, 30000);
    return () => clearInterval(t);
  }, [loadStatus]);

  useEffect(() => {
    loadTab();
  }, [loadTab]);

  const refresh = async () => {
    await Promise.all([loadStatus(), loadTab()]);
  };

  const act = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try {
      await fn();
      if (ok) toast(ok, "success");
      await refresh();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const openThread = async (enrollmentId: string) => {
    try {
      const t = await api(`/enrollments/${enrollmentId}`);
      setThread(t);
      setPhone(t.phone || "");
      setSimText("");
    } catch (e) {
      toast((e as Error).message);
    }
  };

  const reloadThread = async () => {
    if (thread) await openThread(thread.id);
  };

  const draftNow = () =>
    act("draft", async () => {
      const cfg = await api("/settings");
      const job = await api("/run", { method: "POST", json: { draftForTopN: Number(cfg.new_leads_per_day) || 10, minLeadScore: Number(cfg.min_lead_score) || 60 } });
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const j = await api(`/jobs/${job.job_id}`);
        if (j.status === "completed") {
          const r = j.result || {};
          toast(
            r.drafted
              ? `Drafted ${r.drafted} first email${r.drafted === 1 ? "" : "s"} for your top leads.`
              : r.needs_contacts
                ? "No new drafts: top leads still need contacts. Find Leads is looking for them."
                : "No new hot leads to draft for right now.",
            r.drafted ? "success" : "default"
          );
          return;
        }
        if (j.status === "failed") throw new Error(j.error || "Drafting failed");
      }
      throw new Error("Drafting is taking long. It will keep going in the background.");
    });

  const approve = (item: QueueItem, sendNow: boolean) =>
    act(`approve-${item.id}`, async () => {
      const e = edits[item.id];
      if (e && (e.subject !== item.subject || e.body !== item.body)) {
        await api(`/messages/${item.id}`, { method: "PATCH", json: e });
      }
      const r = await api(`/messages/${item.id}/approve?send_now=${sendNow}`, { method: "POST" });
      toast(r.sent ? `Sent to ${item.enrollment.contact_name || item.enrollment.contact_email}.` : r.note, r.sent ? "success" : "default");
    });

  const approveAll = () =>
    act("approve-all", async () => {
      for (const item of queue) {
        const e = edits[item.id];
        if (e && (e.subject !== item.subject || e.body !== item.body)) {
          await api(`/messages/${item.id}`, { method: "PATCH", json: e });
        }
      }
      const r = await api("/queue/approve", { method: "POST", json: { ids: queue.map((q) => q.id), send_now: true } });
      toast(
        `Approved ${r.approved}. Sent ${r.sent} now, the rest go out in sending hours.` +
          (r.held ? ` ${r.held} still need you to fill in the [bracketed] part.` : ""),
        "success",
      );
    });

  const saveSettings = (values: Settings, msg = "Saved.") =>
    act("settings", async () => {
      setSettings(await api("/settings", { method: "PATCH", json: values }));
    }, msg);

  const setAuto = (values: { enabled?: boolean; paused?: boolean }) =>
    act("auto", () => api("/autopilot", { method: "POST", json: values }),
      values.enabled === true ? "Autopilot is on." : values.enabled === false ? "Autopilot is off." : values.paused ? "Everything is paused." : "Resumed.");

  const runNow = () =>
    act("run", async () => {
      const r = await api("/autopilot/run-now", { method: "POST" });
      if (r.error) throw new Error(r.error);
      const sent = (r.follow_ups?.sent || 0) + (r.first_emails || 0);
      toast(`Checked now: ${r.replies?.replies || 0} new replies, ${sent} emails sent, ${r.drafted?.drafted || 0} new drafts.`, "success");
    });

  const autopilotLine = useMemo(() => {
    if (!status) return "";
    if (!status.mailboxes) return "Add a mailbox in Setup to start.";
    if (!status.autopilot_enabled) return "Autopilot is off. Nothing is sent without you.";
    if (status.paused) return "Paused. No emails go out until you resume.";
    return `On. Checks every ${config?.heartbeat_minutes ?? 15} min, next ${when(status.next_heartbeat)}. ${
      status.in_send_window ? "Inside sending hours." : "Outside sending hours, emails wait."
    }`;
  }, [status, config]);

  const tile = (label: string, value: number | string, hint?: string) => (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <p className="text-[11px] text-text-muted">{label}</p>
      <p className="text-lg font-semibold text-text-primary">{value}</p>
      {hint && <p className="text-[10px] text-text-muted">{hint}</p>}
    </div>
  );

  return (
    <div className="space-y-4">
      {loadError && (
        <Alert variant="danger" title="Reach Out service is not answering">
          {loadError}. Start it with scripts/run-local.ps1 (port 8106).
        </Alert>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`h-3 w-3 rounded-full ${
                status?.autopilot_enabled && !status?.paused ? "bg-success animate-pulse" : status?.paused ? "bg-warning" : "bg-border"
              }`}
            />
            <div>
              <p className="text-sm font-semibold text-text-primary">Autopilot</p>
              <p className="text-xs text-text-secondary">{autopilotLine}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {status?.autopilot_enabled ? (
              <Button variant="outline" size="sm" disabled={busy === "auto"} onClick={() => setAuto({ enabled: false })}>
                Turn off
              </Button>
            ) : (
              <Button size="sm" disabled={busy === "auto" || !status?.mailboxes} onClick={() => setAuto({ enabled: true, paused: false })}>
                Turn on autopilot
              </Button>
            )}
            {status?.autopilot_enabled && (
              <Button variant={status.paused ? "primary" : "danger"} size="sm" disabled={busy === "auto"} onClick={() => setAuto({ paused: !status.paused })}>
                {status.paused ? "Resume" : "Pause everything"}
              </Button>
            )}
            <Button variant="outline" size="sm" disabled={busy === "run" || !status?.mailboxes} onClick={runNow}>
              {busy === "run" ? "Checking…" : "Check now"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {status?.sandbox_only && (
        <Alert variant="warning" title="Test mode">
          Only a test mailbox is connected, so nothing is really emailed. Add your Gmail in Setup to go live.
        </Alert>
      )}
      {status && status.approve_first_message && status.waiting_approval > 0 && tab !== "queue" && (
        <Alert title={`${status.waiting_approval} email${status.waiting_approval === 1 ? "" : "s"} waiting for your OK`}>
          <button className="underline" onClick={() => setTab("queue")}>Open the approval queue</button>. Follow-ups and reply sorting happen on their own.
        </Alert>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="today">Today</TabsTrigger>
          <TabsTrigger value="queue">Approve{status?.waiting_approval ? ` (${status.waiting_approval})` : ""}</TabsTrigger>
          <TabsTrigger value="sequences">In progress</TabsTrigger>
          <TabsTrigger value="inbox">Inbox{status?.unread_replies ? ` (${status.unread_replies})` : ""}</TabsTrigger>
          <TabsTrigger value="calls">Calls</TabsTrigger>
          <TabsTrigger value="results">Results</TabsTrigger>
          <TabsTrigger value="setup">Setup</TabsTrigger>
        </TabsList>

        <TabsContent value="today" className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {tile("Sent today", status?.sent_today ?? 0)}
            {tile("Replies today", status?.replies_today ?? 0)}
            {tile("Waiting approval", status?.waiting_approval ?? 0)}
            {tile("In sequence", status?.in_sequence ?? 0)}
            {tile("Hot leads", status?.hot_leads ?? 0, "replied interested")}
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardContent className="space-y-2">
                <p className="text-sm font-semibold text-text-primary">Hot replies to handle</p>
                {!today?.hot_replies?.length && <p className="text-xs text-text-muted">None right now.</p>}
                {today?.hot_replies?.map((r) => (
                  <button key={r.id} onClick={() => r.enrollment_id && openThread(r.enrollment_id)} className="w-full text-left rounded-lg border border-border p-2 hover:border-primary">
                    <div className="flex justify-between gap-2">
                      <span className="text-xs font-medium text-text-primary">{r.lead_name} · {r.contact_name || r.from_email}</span>
                      <Badge variant={CATEGORY_VARIANT[r.category || ""] || "default"}>{r.category_label}</Badge>
                    </div>
                    <p className="text-xs text-text-secondary line-clamp-2 mt-1">{r.body}</p>
                  </button>
                ))}
                <p className="text-sm font-semibold text-text-primary pt-2">Going out in the next 24 hours</p>
                {!today?.due_next_24h?.length && <p className="text-xs text-text-muted">Nothing scheduled.</p>}
                {today?.due_next_24h?.slice(0, 10).map((e) => (
                  <button key={e.id} onClick={() => openThread(e.id)} className="w-full flex justify-between text-left text-xs py-1 border-b border-border/60 hover:text-primary">
                    <span>{e.lead_name} · email {e.current_step + 1}</span>
                    <span className="text-text-muted">{when(e.next_action_at)}</span>
                  </button>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="space-y-1">
                <p className="text-sm font-semibold text-text-primary mb-2">What the autopilot did</p>
                {!events.length && <p className="text-xs text-text-muted">No activity yet.</p>}
                {events.map((ev) => (
                  <div key={ev.id} className="flex justify-between gap-2 text-xs py-1 border-b border-border/60">
                    <span className="text-text-secondary">
                      <span className="text-text-primary">{ev.text}</span>
                      {ev.lead_name ? ` · ${ev.lead_name}` : ""}
                      {ev.kind === "reply" && ev.detail?.category ? ` (${String(ev.detail.category).replace("_", " ")})` : ""}
                      {ev.kind === "sent" && ev.detail?.step ? ` (email ${ev.detail.step})` : ""}
                    </span>
                    <span className="text-text-muted shrink-0">{when(ev.created_at)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="queue" className="space-y-3">
          <div className="flex flex-wrap justify-between items-center gap-2">
            <p className="text-xs text-text-secondary">
              First emails wait here for your OK. Edit anything, then approve. After that the follow-ups run on their own.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={busy === "draft"} onClick={draftNow}>
                {busy === "draft" ? "Writing drafts…" : "Draft emails for top leads"}
              </Button>
              {queue.length > 1 && (
                <Button size="sm" disabled={busy === "approve-all"} onClick={approveAll}>
                  Approve all ({queue.length})
                </Button>
              )}
            </div>
          </div>
          {!queue.length && (
            <EmptyState
              title="Nothing waiting for approval"
              description="Press “Draft emails for top leads”, or turn on autopilot and it will draft for new hot leads every day."
            />
          )}
          {queue.map((item) => {
            const e = edits[item.id] || { subject: item.subject || "", body: item.body || "" };
            return (
              <Card key={item.id}>
                <CardContent className="space-y-2">
                  <div className="flex flex-wrap justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-text-primary">
                        {item.enrollment.lead_name}
                        {item.enrollment.lead_score != null && (
                          <span className="ml-2 text-xs font-normal text-text-muted">score {Math.round(item.enrollment.lead_score)}</span>
                        )}
                      </p>
                      <p className="text-xs text-text-secondary">
                        To {item.enrollment.contact_name || "—"} {item.enrollment.contact_title ? `(${item.enrollment.contact_title})` : ""} &lt;{item.enrollment.contact_email}&gt;
                      </p>
                      {item.enrollment.fit_reason && <p className="text-xs text-text-muted mt-1">Why: {item.enrollment.fit_reason}</p>}
                    </div>
                    <Badge variant={item.kind === "answer" ? "success" : "outline"}>{KIND_LABEL[item.kind] || item.kind}</Badge>
                  </div>
                  <Input value={e.subject} onChange={(ev) => setEdits({ ...edits, [item.id]: { ...e, subject: ev.target.value } })} />
                  <Textarea rows={8} value={e.body} onChange={(ev) => setEdits({ ...edits, [item.id]: { ...e, body: ev.target.value } })} />
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" disabled={busy === `approve-${item.id}`} onClick={() => approve(item, true)}>Approve and send</Button>
                    <Button size="sm" variant="outline" disabled={busy === `approve-${item.id}`} onClick={() => approve(item, false)}>Approve, send in sending hours</Button>
                    <Button size="sm" variant="ghost" disabled={busy === `rw-${item.id}`} onClick={() => act(`rw-${item.id}`, () => api(`/messages/${item.id}/rewrite`, { method: "POST" }), "Rewritten.")}>
                      Rewrite
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => openThread(item.enrollment.id)}>Open thread</Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => act(`rej-${item.id}`, () => api(`/messages/${item.id}/reject`, { method: "POST" }), "Skipped.")}>
                      Skip this lead
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="sequences" className="space-y-3">
          <div className="flex gap-1 flex-wrap">
            {[
              ["active,awaiting_approval,snoozed,replied,interested", "Open"],
              ["active", "In sequence"],
              ["interested,replied", "Replied"],
              ["snoozed", "Snoozed"],
              ["completed,stopped", "Finished"],
              ["bounced,unsubscribed", "Bounced / unsubscribed"],
            ].map(([v, l]) => (
              <button key={v} onClick={() => setStatusFilter(v)} className={`text-xs px-3 py-1 rounded-lg border ${statusFilter === v ? "border-primary text-primary bg-primary/10" : "border-border text-text-muted"}`}>
                {l}
              </button>
            ))}
          </div>
          {!enrollments.length && <EmptyState title="No one here yet" description="Approved leads show up here with their next email date." />}
          <div className="space-y-1">
            {enrollments.map((e) => (
              <button key={e.id} onClick={() => openThread(e.id)} className="w-full text-left rounded-lg border border-border bg-surface p-3 hover:border-primary flex flex-wrap justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{e.lead_name} · {e.contact_name || e.contact_email}</p>
                  <p className="text-xs text-text-muted truncate">{e.contact_title || e.contact_email}</p>
                </div>
                <div className="flex items-center gap-3 text-xs text-text-secondary">
                  <span>email {e.current_step}/4</span>
                  {e.status === "active" && e.next_action_at && <span>next {when(e.next_action_at)}</span>}
                  <Badge variant={STATUS_VARIANT[e.status] || "default"}>{STATUS_LABEL[e.status] || e.status}</Badge>
                </div>
              </button>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="inbox" className="space-y-2">
          <p className="text-xs text-text-secondary">Replies are read every check and sorted by AI. The action already taken is shown on each one.</p>
          {!inbox.length && <EmptyState title="No replies yet" description="Replies land here automatically once emails go out." />}
          {inbox.map((r) => (
            <Card key={r.id} className={r.handled ? "opacity-70" : ""}>
              <CardContent className="space-y-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="text-sm font-medium text-text-primary">{r.lead_name || "Unknown lead"} · {r.contact_name || r.from_email}</p>
                  <div className="flex items-center gap-2">
                    <Badge variant={CATEGORY_VARIANT[r.category || ""] || "default"}>{r.category_label}</Badge>
                    <span className="text-xs text-text-muted">{when(r.received_at)}</span>
                  </div>
                </div>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">{r.body}</p>
                {r.action_taken && <p className="text-xs text-success">Done: {r.action_taken}</p>}
                <div className="flex gap-2 pt-1">
                  {r.enrollment_id && <Button size="sm" variant="outline" onClick={() => openThread(r.enrollment_id!)}>Open thread</Button>}
                  {!r.handled && (
                    <Button size="sm" variant="ghost" onClick={() => act(`h-${r.id}`, () => api(`/replies/${r.id}/handled`, { method: "POST" }))}>
                      Mark done
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="calls" className="space-y-3">
          {!config?.calls_configured ? (
            <Alert title="AI calls are not connected yet">
              Calls use a self-hosted Dograh voice agent. Add DOGRAH_API_URL, DOGRAH_API_KEY and DOGRAH_WORKFLOW_ID to .env,
              then point the Dograh webhook node to: <code className="break-all">{config?.calls_webhook_url}</code>. The agent must say it is an AI and that the call may be recorded.
            </Alert>
          ) : (
            <Alert variant="success" title="AI calls are connected">
              Calls start after email {String(settings.call_after_step ?? 2)} gets no reply for {String(settings.call_wait_days ?? 2)} days, weekdays 10:00 to 17:00, and only when “calls” is on in Setup.
            </Alert>
          )}
          {!calls.length && <EmptyState title="No calls yet" description="Calls appear here with their outcome and summary." />}
          {calls.map((c) => (
            <Card key={c.id}>
              <CardContent className="space-y-1">
                <div className="flex justify-between gap-2">
                  <p className="text-sm font-medium text-text-primary">{[c.lead_name, c.contact_name, c.phone].filter(Boolean).join(" · ")}</p>
                  <Badge variant={c.outcome === "interested" ? "success" : c.status === "failed" ? "danger" : "outline"}>{(c.outcome || c.status).replace("_", " ")}</Badge>
                </div>
                {c.summary && <p className="text-xs text-text-secondary">{c.summary}</p>}
                {c.error && <p className="text-xs text-danger">{c.error}</p>}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="results" className="space-y-4">
          {report && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {tile("Emails sent (30 days)", report.totals.emails_sent)}
                {tile("People replied", report.totals.people_replied, pct(report.totals.reply_rate))}
                {tile("Interested", report.totals.interested)}
                {tile("Bounced", report.totals.bounced)}
                {tile("Unsubscribed", report.totals.unsubscribed)}
              </div>
              <Card>
                <CardContent className="space-y-2">
                  <p className="text-sm font-semibold text-text-primary">What the AI learned</p>
                  {report.learnings.length ? (
                    report.learnings.map((l) => <p key={l} className="text-xs text-text-secondary">• {l}</p>)
                  ) : (
                    <p className="text-xs text-text-muted">Needs a few more sends and replies. The writer uses these lessons automatically.</p>
                  )}
                </CardContent>
              </Card>
              <div className="grid md:grid-cols-2 gap-4">
                <Card>
                  <CardContent>
                    <p className="text-sm font-semibold text-text-primary mb-2">Replies by email step</p>
                    <table className="w-full text-xs">
                      <thead className="text-text-muted"><tr><th className="text-left">Step</th><th>Sent</th><th>Replies</th><th>Rate</th></tr></thead>
                      <tbody>
                        {report.by_step.map((s) => (
                          <tr key={s.step} className="border-t border-border/60 text-center"><td className="text-left py-1">Email {s.step}</td><td>{s.sent}</td><td>{s.replies}</td><td>{pct(s.reply_rate)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <p className="text-sm font-semibold text-text-primary mb-2">Best subject lines</p>
                    <table className="w-full text-xs">
                      <thead className="text-text-muted"><tr><th className="text-left">Subject</th><th>Sent</th><th>Rate</th></tr></thead>
                      <tbody>
                        {report.by_subject.map((s) => (
                          <tr key={s.subject} className="border-t border-border/60 text-center"><td className="text-left py-1 truncate max-w-[220px]">{s.subject}</td><td>{s.sent}</td><td>{pct(s.reply_rate)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="setup" className="space-y-4">
          <Card>
            <CardContent className="space-y-3">
              <p className="text-sm font-semibold text-text-primary">Mailboxes</p>
              <p className="text-xs text-text-secondary">
                Emails go from your own Gmail. Use a Google App Password (Google account → Security → App passwords), not your normal password.
                Each mailbox starts at 20 emails a day and grows by 5 a day up to 50. Passwords are stored encrypted.
              </p>
              {mailboxes.map((m) => (
                <div key={m.id} className="rounded-lg border border-border p-3 flex flex-wrap justify-between gap-2">
                  <div>
                    <p className="text-sm text-text-primary">{m.email} {m.kind === "sandbox" && <Badge variant="warning">test</Badge>} {!m.active && <Badge variant="danger">paused</Badge>}</p>
                    <p className="text-xs text-text-muted">
                      {m.sent_today}/{m.daily_cap_today} today · {m.sent_total} sent total · bounce rate {pct(m.bounce_rate)}
                    </p>
                    {m.paused_reason && <p className="text-xs text-danger">{m.paused_reason}</p>}
                    {m.last_error && <p className="text-xs text-danger">{m.last_error}</p>}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={busy === `t-${m.id}`} onClick={() => act(`t-${m.id}`, async () => {
                      const r = await api(`/mailboxes/${m.id}/test`, { method: "POST" });
                      toast(r.smtp && r.imap ? "Connection works." : `Problem: ${r.error}`, r.smtp && r.imap ? "success" : "default");
                    })}>Test</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(`p-${m.id}`, () => api(`/mailboxes/${m.id}`, { method: "PATCH", json: { active: !m.active } }))}>
                      {m.active ? "Pause" : "Resume"}
                    </Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => act(`d-${m.id}`, () => api(`/mailboxes/${m.id}`, { method: "DELETE" }), "Removed.")}>Remove</Button>
                  </div>
                </div>
              ))}
              <div className="grid md:grid-cols-3 gap-2">
                <Input placeholder="you@gmail.com" value={newBox.email} onChange={(e) => setNewBox({ ...newBox, email: e.target.value })} />
                <Input placeholder="App password" type="password" value={newBox.password} onChange={(e) => setNewBox({ ...newBox, password: e.target.value })} />
                <Input placeholder="Your name (shown as sender)" value={newBox.from_name} onChange={(e) => setNewBox({ ...newBox, from_name: e.target.value })} />
                {newBox.email && !/@(gmail|googlemail)\.com$/i.test(newBox.email) && (
                  <>
                    <Input placeholder="SMTP server, e.g. smtp.office365.com" value={newBox.smtp_host} onChange={(e) => setNewBox({ ...newBox, smtp_host: e.target.value })} />
                    <Input placeholder="IMAP server, e.g. outlook.office365.com" value={newBox.imap_host} onChange={(e) => setNewBox({ ...newBox, imap_host: e.target.value })} />
                  </>
                )}
              </div>
              <div className="flex gap-2">
                <Button size="sm" disabled={!newBox.email || !newBox.password || busy === "addbox"} onClick={() => act("addbox", async () => {
                  const body: Record<string, string> = { email: newBox.email, password: newBox.password, from_name: newBox.from_name };
                  if (newBox.smtp_host) body.smtp_host = newBox.smtp_host;
                  if (newBox.imap_host) body.imap_host = newBox.imap_host;
                  const mb = await api("/mailboxes", { method: "POST", json: body });
                  setNewBox({ email: "", password: "", from_name: "", smtp_host: "", imap_host: "" });
                  const r = await api(`/mailboxes/${mb.id}/test`, { method: "POST" });
                  toast(r.smtp && r.imap ? "Mailbox added and working." : `Added, but the test failed: ${r.error}`, r.smtp && r.imap ? "success" : "default");
                })}>Add mailbox</Button>
                {!mailboxes.some((m) => m.kind === "sandbox") && (
                  <Button size="sm" variant="outline" onClick={() => act("sandbox", () => api("/mailboxes", { method: "POST", json: { kind: "sandbox" } }), "Test mailbox added.")}>
                    Add a test mailbox (sends nothing)
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          <SettingsCard settings={settings} onSave={saveSettings} busy={busy === "settings"} />

          {sequence && (
            <Card>
              <CardContent className="space-y-2">
                <p className="text-sm font-semibold text-text-primary">The email sequence</p>
                <p className="text-xs text-text-secondary">Each step is written fresh by AI for the lead. Only the last one includes your booking link.</p>
                {sequence.steps.map((s, i) => (
                  <div key={s.step} className="flex items-center gap-2 text-xs">
                    <span className="w-16 text-text-muted">Email {s.step}</span>
                    <Input className="flex-1" value={s.label} onChange={(e) => {
                      const steps = [...sequence.steps];
                      steps[i] = { ...s, label: e.target.value };
                      setSequence({ ...sequence, steps });
                    }} />
                    {s.step > 1 && (
                      <>
                        <Input className="w-16" type="number" min={1} value={s.wait_days} onChange={(e) => {
                          const steps = [...sequence.steps];
                          steps[i] = { ...s, wait_days: Number(e.target.value) };
                          setSequence({ ...sequence, steps });
                        }} />
                        <span className="text-text-muted">days later</span>
                      </>
                    )}
                  </div>
                ))}
                <Button size="sm" variant="outline" disabled={busy === "seq"} onClick={() => act("seq", () => api(`/sequences/${sequence.id}`, { method: "PUT", json: { steps: sequence.steps } }), "Sequence saved.")}>
                  Save sequence
                </Button>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="space-y-2">
              <p className="text-sm font-semibold text-text-primary">Connections</p>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant={config?.openai_configured ? "success" : "muted"}>AI writer {config?.openai_configured ? "on" : "off (using templates)"}</Badge>
                <Badge variant={config?.alerts?.slack ? "success" : "muted"}>Slack</Badge>
                <Badge variant={config?.alerts?.telegram ? "success" : "muted"}>Telegram</Badge>
                <Badge variant={config?.crm?.hubspot ? "success" : "muted"}>HubSpot</Badge>
                <Badge variant={config?.crm?.twenty ? "success" : "muted"}>Twenty CRM</Badge>
                <Badge variant={config?.calls_configured ? "success" : "muted"}>AI calls</Badge>
              </div>
              <p className="text-xs text-text-muted">Keys live in .env on the server (SLACK_WEBHOOK_URL, TELEGRAM_BOT_TOKEN, HUBSPOT_ACCESS_TOKEN, TWENTY_API_KEY, DOGRAH_API_KEY).</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={busy === "alert"} onClick={() => act("alert", () => api("/alerts/test", { method: "POST" }), "Test alert sent.")}>Send test alert</Button>
                <Button size="sm" variant="outline" disabled={busy === "crm"} onClick={() => act("crm", async () => {
                  const r = await api("/crm/sync", { method: "POST" });
                  toast(`Synced ${r.synced} people to the CRM.`, "success");
                })}>Sync to CRM now</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Sheet open={!!thread} onOpenChange={(o) => !o && setThread(null)}>
        <SheetContent className="overflow-y-auto sm:max-w-xl">
          {thread && (
            <>
              <SheetHeader>
                <SheetTitle>{thread.lead_name} · {thread.contact_name || thread.contact_email}</SheetTitle>
              </SheetHeader>
              <div className="space-y-3 mt-3">
                <div className="flex flex-wrap gap-2 items-center text-xs">
                  <Badge variant={STATUS_VARIANT[thread.status] || "default"}>{STATUS_LABEL[thread.status] || thread.status}</Badge>
                  <span className="text-text-muted">{thread.contact_title} · {thread.contact_email}</span>
                </div>
                {thread.fit_reason && <p className="text-xs text-text-secondary">Why this lead: {thread.fit_reason}</p>}
                <div className="flex flex-wrap gap-2">
                  {["active", "awaiting_approval", "snoozed", "replied", "interested"].includes(thread.status) ? (
                    <Button size="sm" variant="outline" onClick={() => act("stop", () => api(`/enrollments/${thread.id}/stop`, { method: "POST" }), "Stopped.").then(reloadThread)}>Stop emails</Button>
                  ) : (
                    !["unsubscribed", "bounced"].includes(thread.status) && (
                      <Button size="sm" variant="outline" onClick={() => act("resume", () => api(`/enrollments/${thread.id}/resume`, { method: "POST" }), "Resumed.").then(reloadThread)}>Resume</Button>
                    )
                  )}
                </div>

                <div className="space-y-2">
                  {[
                    ...thread.messages.map((m) => ({ at: m.sent_at || m.created_at || "", node: (
                      <div key={m.id} className="rounded-lg border border-border p-2">
                        <div className="flex justify-between text-[11px] text-text-muted">
                          <span>{KIND_LABEL[m.kind] || m.kind} · email {m.step}</span>
                          <span>{m.status === "sent" ? `sent ${when(m.sent_at)}` : m.status}</span>
                        </div>
                        <p className="text-xs font-medium text-text-primary mt-1">{m.subject}</p>
                        <p className="text-xs text-text-secondary whitespace-pre-wrap">{m.body}</p>
                        {m.error && <p className="text-xs text-danger">{m.error}</p>}
                      </div>
                    ) })),
                    ...thread.replies.map((r) => ({ at: r.received_at || "", node: (
                      <div key={r.id} className="rounded-lg border border-success/40 bg-success/5 p-2 ml-6">
                        <div className="flex justify-between text-[11px] text-text-muted">
                          <span>Their reply</span>
                          <Badge variant={CATEGORY_VARIANT[r.category || ""] || "default"}>{r.category_label}</Badge>
                        </div>
                        <p className="text-xs text-text-primary whitespace-pre-wrap mt-1">{r.body}</p>
                        {r.action_taken && <p className="text-[11px] text-success mt-1">Done: {r.action_taken}</p>}
                      </div>
                    ) })),
                    ...thread.calls.map((c) => ({ at: c.created_at || "", node: (
                      <div key={c.id} className="rounded-lg border border-border p-2 text-xs">
                        AI call to {c.phone}: {(c.outcome || c.status).replace("_", " ")} {c.summary ? `· ${c.summary}` : ""}
                      </div>
                    ) })),
                  ]
                    .sort((a, b) => a.at.localeCompare(b.at))
                    .map((x) => x.node)}
                </div>

                {thread.status === "active" && thread.next_action_at && (
                  <p className="text-xs text-text-muted">Next email ({thread.steps.find((s) => s.step === thread.current_step + 1)?.label || "finish"}) {when(thread.next_action_at)}.</p>
                )}

                <div className="rounded-lg border border-border p-2 space-y-2">
                  <p className="text-xs font-medium text-text-primary">Phone for AI call</p>
                  <div className="flex gap-2">
                    <Input placeholder="+14155550123" value={phone} onChange={(e) => setPhone(e.target.value)} />
                    <Button size="sm" variant="outline" onClick={() => act("phone", () => api(`/enrollments/${thread.id}/phone`, { method: "PATCH", json: { phone } }), "Saved.").then(reloadThread)}>Save</Button>
                    {config?.calls_configured && thread.phone && (
                      <Button size="sm" onClick={() => act("call", () => api(`/enrollments/${thread.id}/call`, { method: "POST" }), "Call started.").then(reloadThread)}>Call now</Button>
                    )}
                  </div>
                </div>

                {status?.sandbox_only && thread.current_step > 0 && (
                  <div className="rounded-lg border border-dashed border-warning/50 p-2 space-y-2">
                    <p className="text-xs font-medium text-text-primary">Test: pretend they replied</p>
                    <div className="flex flex-wrap gap-1">
                      {SAMPLE_REPLIES.map((s) => (
                        <button key={s.label} className="text-[11px] px-2 py-0.5 rounded border border-border hover:border-primary" onClick={() => setSimText(s.text)}>{s.label}</button>
                      ))}
                    </div>
                    <Textarea rows={3} value={simText} onChange={(e) => setSimText(e.target.value)} placeholder="Type a reply…" />
                    <Button size="sm" variant="outline" disabled={!simText || busy === "sim"} onClick={() => act("sim", async () => {
                      const r = await api("/replies/simulate", { method: "POST", json: { enrollment_id: thread.id, body: simText } });
                      toast(`Sorted as “${r.reply.category_label}”. ${r.reply.action_taken || ""}`, "success");
                    }).then(reloadThread)}>Send test reply</Button>
                  </div>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SettingsCard({ settings, onSave, busy }: { settings: Settings; onSave: (v: Settings, msg?: string) => void; busy: boolean }) {
  const [form, setForm] = useState<Settings>(settings);
  useEffect(() => setForm(settings), [settings]);
  const field = (key: string, label: string, type: "text" | "number" = "text", placeholder?: string) => (
    <label className="text-xs text-text-secondary space-y-1">
      <span>{label}</span>
      <Input
        type={type}
        placeholder={placeholder}
        value={String(form[key] ?? "")}
        onChange={(e) => setForm({ ...form, [key]: type === "number" ? Number(e.target.value) : e.target.value })}
      />
    </label>
  );
  const toggle = (key: string, label: string) => (
    <label className="flex items-center gap-2 text-xs text-text-secondary">
      <input type="checkbox" checked={!!form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />
      {label}
    </label>
  );
  return (
    <Card>
      <CardContent className="space-y-3">
        <p className="text-sm font-semibold text-text-primary">How the autopilot works</p>
        <div className="grid md:grid-cols-3 gap-3">
          {field("sender_name", "Your name")}
          {field("company_name", "Company")}
          {field("booking_link", "Booking link", "text", "https://cal.com/you/intro")}
          {field("min_lead_score", "Only leads with score at least", "number")}
          {field("new_leads_per_day", "New leads per day", "number")}
          {field("max_contacts_per_company", "Max people per company", "number")}
          {field("send_start_hour", "Send from (hour)", "number")}
          {field("send_end_hour", "Send until (hour)", "number")}
          {field("timezone", "Time zone", "text", "Asia/Kolkata")}
          {field("snooze_days", "'Not now' snooze (days)", "number")}
          {field("call_after_step", "AI call after email #", "number")}
          {field("call_wait_days", "…if no reply after (days)", "number")}
        </div>
        <label className="text-xs text-text-secondary space-y-1 block">
          <span>What we do (one line, used by the writer)</span>
          <Textarea rows={2} value={String(form.value_prop ?? "")} onChange={(e) => setForm({ ...form, value_prop: e.target.value })} />
        </label>
        <label className="text-xs text-text-secondary space-y-1 block">
          <span>Signature</span>
          <Textarea rows={3} value={String(form.signature ?? "")} onChange={(e) => setForm({ ...form, signature: e.target.value })} />
        </label>
        <label className="text-xs text-text-secondary space-y-1 block">
          <span>Never call these numbers (one per line)</span>
          <Textarea
            rows={2}
            value={Array.isArray(form.dnd_numbers) ? (form.dnd_numbers as string[]).join("\n") : ""}
            onChange={(e) => setForm({ ...form, dnd_numbers: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })}
          />
        </label>
        <div className="flex flex-wrap gap-4">
          {toggle("approve_first_message", "I approve every first email")}
          {toggle("send_weekends", "Send on weekends")}
          {toggle("alerts_enabled", "Alert the team on hot replies")}
          {toggle("daily_report_enabled", "Daily summary to Slack/Telegram")}
          {toggle("crm_sync_enabled", "Sync to CRM")}
          {toggle("calls_enabled", "AI calls (needs Dograh)")}
        </div>
        <Button size="sm" disabled={busy} onClick={() => onSave(form, "Settings saved.")}>Save settings</Button>
      </CardContent>
    </Card>
  );
}
