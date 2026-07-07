"use client";

import { useEffect, useState } from "react";
import { CONNECTORS } from "@/lib/connectors";
import { PageHeader, Card, CardContent, StatusDot, Badge } from "@tool-hub/ui";

export default function IntegrationsPage() {
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch("/api/hub/status")
      .then((r) => r.json())
      .then((d) => {
        setStatuses({
          openai: !!d.integrations?.openai,
          github: !!d.integrations?.github,
          adzuna: !!d.integrations?.adzuna,
          hunter: !!d.integrations?.hunter,
          apollo: !!process.env.NEXT_PUBLIC_APOLLO,
        });
      })
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrations"
        description="Live data sources powering market scoring, proof indexing, and lead enrichment."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map((c) => {
          const connected = c.type === "public" || !!statuses[c.id];
          return (
            <Card key={c.id}>
              <CardContent className="pt-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-semibold text-text-primary">{c.name}</p>
                    <Badge variant="outline" className="mt-1 text-[10px]">
                      {c.type}
                    </Badge>
                  </div>
                  <StatusDot
                    variant={connected ? "success" : "warning"}
                    label={c.type === "public" ? "Public API" : connected ? "Connected" : "Not configured"}
                  />
                </div>
                <p className="text-sm text-text-secondary leading-relaxed">{c.description}</p>
                <p className="text-xs text-text-muted mt-3">Used by: {c.usedByModules.join(", ")}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
