"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  Label,
  useToast,
} from "@tool-hub/ui";
import { errorMessage, fmtDate, useApi } from "../api";
import { RecipesCard } from "./dealroom";

type Account = {
  id: string;
  lead_id: string;
  name: string;
  domain?: string;
  track?: string;
  score?: number;
  is_portal: boolean;
  unread_alerts: number;
  last_checked_at?: string | null;
};

type InsiderAlert = {
  id: string;
  lead_id: string;
  account_name: string;
  alert_type: string;
  severity: "low" | "medium" | "high";
  title: string;
  detail?: string;
  url?: string;
  read: boolean;
  created_at: string;
};

const SEVERITY_VARIANT = { low: "muted", medium: "warning", high: "danger" } as const;

export default function InsiderTab({ onChange }: { onChange: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [alerts, setAlerts] = useState<InsiderAlert[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [size, setSize] = useState("25");
  const [minScore, setMinScore] = useState("40");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [w, a] = await Promise.all([
        api.get<{ accounts: Account[] }>("/watchlist"),
        api.get<{ alerts: InsiderAlert[] }>(`/alerts?limit=150${unreadOnly ? "&unread_only=true" : ""}`),
      ]);
      setAccounts(w.accounts);
      setAlerts(a.alerts);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api, unreadOnly]);

  useEffect(() => {
    load();
  }, [load]);

  const sync = async () => {
    setBusy("sync");
    try {
      const r = await api.post<{ accounts_added: number; leads_considered: number }>("/watchlist/sync", {
        size: parseInt(size, 10) || 25,
        min_lead_score: parseFloat(minScore) || 0,
      });
      toast(`Added ${r.accounts_added} of ${r.leads_considered} top leads to the watchlist`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const scan = async () => {
    setBusy("scan");
    try {
      const { job_id } = await api.post<{ job_id: string }>("/insider/scan");
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Scan failed");
      else toast(`Scanned ${job.result.accounts_scanned ?? 0} accounts, ${job.result.alerts_created ?? 0} new alerts`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const markRead = async (id: string) => {
    await api.patch(`/alerts/${id}`, { read: true });
    load();
    onChange();
  };

  const markAll = async () => {
    await api.post("/alerts/read-all");
    load();
    onChange();
  };

  const unwatch = async (id: string) => {
    await api.del(`/watchlist/${id}`);
    load();
    onChange();
  };

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger" title="Failed to load insider data">{error}</Alert>}

      <RecipesCard onChange={onChange} />

      <Card>
        <CardHeader>
          <CardTitle>Accounts we're watching</CardTitle>
          <CardDescription>
            The agent re-checks every watched account on a schedule: score changes, new signals, deadlines, company
            news and hiring spikes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label>Top leads to watch</Label>
              <Input className="w-28" type="number" value={size} onChange={(e) => setSize(e.target.value)} />
            </div>
            <div>
              <Label>Min lead score</Label>
              <Input className="w-28" type="number" value={minScore} onChange={(e) => setMinScore(e.target.value)} />
            </div>
            <Button variant="outline" onClick={sync} disabled={!!busy}>
              {busy === "sync" ? "Syncing…" : "Sync from top leads"}
            </Button>
            <Button onClick={scan} disabled={!!busy || accounts.length === 0}>
              {busy === "scan" ? "Scanning…" : "Scan now"}
            </Button>
          </div>

          {accounts.length === 0 ? (
            <EmptyState title="No watched accounts" description="Sync from your top-scored leads to start watching them." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-text-muted text-left">
                  <tr>
                    <th className="py-2 pr-3">Account</th>
                    <th className="py-2 pr-3">Track</th>
                    <th className="py-2 pr-3">Score</th>
                    <th className="py-2 pr-3">New alerts</th>
                    <th className="py-2 pr-3">Last checked</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id} className="border-t border-border">
                      <td className="py-2 pr-3">
                        <p className="font-medium">{a.name}</p>
                        <p className="text-xs text-text-muted">{a.domain || (a.is_portal ? "government tender" : "—")}</p>
                      </td>
                      <td className="py-2 pr-3 text-xs uppercase">{a.track || "—"}</td>
                      <td className="py-2 pr-3 text-xs">{a.score != null ? a.score.toFixed(0) : "—"}</td>
                      <td className="py-2 pr-3">
                        {a.unread_alerts > 0 ? <Badge variant="warning">{a.unread_alerts}</Badge> : <span className="text-xs text-text-muted">0</span>}
                      </td>
                      <td className="py-2 pr-3 text-xs">{fmtDate(a.last_checked_at)}</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => unwatch(a.id)}>
                          Unwatch
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Alerts feed</h3>
        <div className="flex gap-2">
          <Button size="sm" variant={unreadOnly ? "primary" : "outline"} onClick={() => setUnreadOnly((u) => !u)}>
            {unreadOnly ? "Showing unread" : "Show unread only"}
          </Button>
          <Button size="sm" variant="ghost" onClick={markAll}>
            Mark all read
          </Button>
        </div>
      </div>

      {alerts.length === 0 ? (
        <EmptyState title="No alerts" description="Alerts appear here after a scan finds something new." />
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => (
            <Card key={a.id} className={a.read ? "opacity-60" : undefined}>
              <CardContent className="py-3 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={SEVERITY_VARIANT[a.severity]}>{a.severity}</Badge>
                    <Badge variant="outline">{a.alert_type.replace(/_/g, " ")}</Badge>
                    <span className="text-xs text-text-muted">{fmtDate(a.created_at)}</span>
                  </div>
                  <p className="text-sm font-medium">{a.title}</p>
                  {a.detail && <p className="text-xs text-text-secondary">{a.detail}</p>}
                </div>
                <div className="flex gap-2 shrink-0">
                  {a.url && (
                    <Button size="sm" variant="outline" asChild>
                      <a href={a.url} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    </Button>
                  )}
                  {!a.read && (
                    <Button size="sm" variant="ghost" onClick={() => markRead(a.id)}>
                      Mark read
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
