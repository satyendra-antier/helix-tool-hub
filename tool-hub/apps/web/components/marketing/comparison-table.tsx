const ROWS = [
  { dim: "Core output", agents: "Open-ended text and code", hub: "Scored verdicts, ranked pipeline, cited proof" },
  { dim: "Data foundation", agents: "Session context, web search", hub: "Live public signals + customer proof graph" },
  { dim: "Repeatability", agents: "Ad-hoc prompts", hub: "Weekly deterministic refresh cadence" },
  { dim: "Trust model", agents: "Model opinion", hub: "Algorithmic scores + RAG citations from your content" },
  { dim: "GTM action", agents: "Draft suggestions", hub: "Demand vs future lead framework + human-reviewed outreach" },
];

export function ComparisonTable() {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-surface-muted text-left">
            <th className="p-4 font-medium text-text-muted w-1/4" />
            <th className="p-4 font-medium text-text-secondary">AI agents (Claude, Cursor, Gemini)</th>
            <th className="p-4 font-medium text-text-primary">LeadGen AI</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.dim} className="border-b border-border last:border-0">
              <td className="p-4 font-medium text-text-primary">{r.dim}</td>
              <td className="p-4 text-text-secondary">{r.agents}</td>
              <td className="p-4 text-text-primary">{r.hub}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
