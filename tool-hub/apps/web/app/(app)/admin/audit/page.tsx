"use client";

import { useEffect, useState } from "react";
import type { AuditLogEntry } from "@tool-hub/shared-types";
import { PageHeader, Card, CardContent } from "@tool-hub/ui";

export default function AdminAuditPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);

  useEffect(() => {
    fetch("/api/hub/audit")
      .then((r) => r.json())
      .then((d) => setEntries(d.entries || []));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title="Audit Log" description="Admin actions, logins, pipeline runs, and configuration changes." />
      <Card>
        <CardContent className="pt-6">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="pb-2 pr-4 font-medium">Time</th>
                  <th className="pb-2 pr-4 font-medium">User</th>
                  <th className="pb-2 pr-4 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-border/60">
                    <td className="py-2 pr-4 text-text-secondary whitespace-nowrap">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="py-2 pr-4">{e.user_email || e.user_name || "—"}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{e.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {entries.length === 0 ? <p className="text-sm text-text-muted py-4">No audit entries yet.</p> : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
