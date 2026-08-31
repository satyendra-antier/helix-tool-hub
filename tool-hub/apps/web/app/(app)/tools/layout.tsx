import { loadToolRegistry, resolveBackendUrl } from "@/lib/registry";
import { ToolsKeepAlive } from "@/components/tools-keep-alive";

export default function ToolsLayout({ children }: { children: React.ReactNode }) {
  const tools = loadToolRegistry();
  const backends = Object.fromEntries(
    tools.map((t) => [t.id, resolveBackendUrl(t)])
  );
  const vault: Record<string, string> = {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY || "",
    GITHUB_TOKEN: process.env.GITHUB_TOKEN || "",
    ADZUNA_APP_ID: process.env.ADZUNA_APP_ID || "",
    APOLLO_API_KEY: process.env.APOLLO_API_KEY || "",
    HUNTER_API_KEY: process.env.HUNTER_API_KEY || "",
    SAM_GOV_API_KEY: process.env.SAM_GOV_API_KEY || "",
  };

  return (
    <>
      <ToolsKeepAlive tools={tools} backends={backends} vault={vault} />
      {children}
    </>
  );
}
