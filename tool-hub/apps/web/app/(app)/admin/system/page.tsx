"use client";

import { useEffect, useState } from "react";
import { PageHeader, Card, CardContent, StatusDot } from "@tool-hub/ui";

export default function AdminSystemPage() {
  const [health, setHealth] = useState<Array<{ slug: string; ok: boolean }>>([]);
  const [integrations, setIntegrations] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch("/api/hub/status")
      .then((r) => r.json())
      .then((d) => {
        setHealth(d.health || []);
        setIntegrations(d.integrations || {});
      });
  }, []);

  const secrets = [
    { key: "OPENAI_API_KEY", ok: integrations.openai },
    { key: "GITHUB_TOKEN", ok: integrations.github },
    { key: "ADZUNA", ok: integrations.adzuna },
    { key: "HUNTER_API_KEY", ok: integrations.hunter },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="System Health" description="Module services and integration configuration status." />
      <Card>
        <CardContent className="pt-6 divide-y divide-border">
          <p className="text-xs font-medium text-text-muted uppercase mb-3">Module APIs</p>
          {health.map((h) => (
            <div key={h.slug} className="flex items-center justify-between py-3">
              <span className="text-sm font-medium">{h.slug}</span>
              <StatusDot variant={h.ok ? "success" : "danger"} label={h.ok ? "Healthy" : "Unreachable"} />
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6 divide-y divide-border">
          <p className="text-xs font-medium text-text-muted uppercase mb-3">Secrets (configured / missing)</p>
          {secrets.map((s) => (
            <div key={s.key} className="flex items-center justify-between py-3">
              <span className="font-mono text-xs">{s.key}</span>
              <StatusDot variant={s.ok ? "success" : "warning"} label={s.ok ? "Configured" : "Missing"} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
