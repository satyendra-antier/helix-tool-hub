"use client";

import { useState } from "react";

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);

  return (
    <div className="max-w-xl mx-auto px-6 py-12">
      <h1 className="font-display text-2xl font-bold mb-2">Vault / Settings</h1>
      <p className="text-text-secondary text-sm mb-8 leading-relaxed">
        API keys are configured via environment variables in Docker. Edit{" "}
        <code className="font-mono text-xs bg-panel px-1.5 py-0.5 rounded border border-border">
          .env
        </code>{" "}
        and restart with{" "}
        <code className="font-mono text-xs bg-panel px-1.5 py-0.5 rounded border border-border">
          ./start.sh restart
        </code>
        .
      </p>

      <div className="bg-panel border border-border rounded-lg p-6 space-y-4">
        <h2 className="font-mono text-xs text-text-dim uppercase tracking-wider">
          Required keys
        </h2>
        {[
          "OPENAI_API_KEY",
          "GITHUB_TOKEN",
          "ADZUNA_APP_ID",
          "ADZUNA_APP_KEY",
          "APOLLO_API_KEY",
          "HUNTER_API_KEY",
          "SAM_GOV_API_KEY",
        ].map((key) => (
          <div key={key} className="flex justify-between items-center py-2 border-b border-border last:border-0">
            <span className="font-mono text-sm">{key}</span>
            <span className="font-mono text-xs text-text-dim">
              set in .env
            </span>
          </div>
        ))}
      </div>

      <button
        onClick={() => setSaved(true)}
        className="mt-6 font-mono text-xs border border-border-bright text-text-secondary px-4 py-2 rounded hover:border-text-primary hover:text-text-primary transition-colors"
      >
        {saved ? "Keys loaded from .env on restart" : "Acknowledge"}
      </button>
    </div>
  );
}
