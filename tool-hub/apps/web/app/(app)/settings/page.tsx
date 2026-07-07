import { PageHeader, Card, CardContent, StatusDot } from "@tool-hub/ui";

const INTEGRATIONS = [
  { key: "OPENAI_API_KEY", label: "OpenAI", note: "Shared fallback for all tools", env: "OPENAI_API_KEY" },
  { key: "GITHUB_TOKEN", label: "GitHub", note: "Market signals", env: "GITHUB_TOKEN" },
  { key: "ADZUNA_APP_ID", label: "Adzuna", note: "Job listings", env: "ADZUNA_APP_ID" },
  { key: "HUNTER_API_KEY", label: "Hunter", note: "Contact enrichment", env: "HUNTER_API_KEY" },
  { key: "SAM_GOV_API_KEY", label: "SAM.gov", note: "Government leads", env: "SAM_GOV_API_KEY" },
];

function isConfigured(envKey: string): boolean {
  return !!(process.env[envKey] || (envKey !== "OPENAI_API_KEY" && process.env.OPENAI_API_KEY));
}

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Platform configuration. API secrets are loaded from environment variables."
      />
      <Card>
        <CardContent className="divide-y divide-border pt-6">
          {INTEGRATIONS.map(({ key, label, note, env }) => {
            const configured = isConfigured(env);
            return (
              <div key={key} className="flex items-center justify-between py-4 first:pt-0 last:pb-0">
                <div>
                  <p className="text-sm font-medium text-text-primary">{label}</p>
                  <p className="text-xs text-text-secondary mt-0.5">{note}</p>
                  <p className="font-mono text-xs text-text-muted mt-1">{key}</p>
                </div>
                <StatusDot variant={configured ? "success" : "muted"} label={configured ? "Configured" : "Not set"} />
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
