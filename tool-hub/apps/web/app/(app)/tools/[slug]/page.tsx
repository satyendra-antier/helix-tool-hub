import { notFound } from "next/navigation";
import { getToolBySlug, resolveBackendUrl } from "@/lib/registry";
import { ToolProvider } from "@/lib/tool-context";
import { ToolHost } from "@/components/tool-host";
import { ModuleAccentShell, ModulePageHeader } from "@/components/module-page-header";

export const dynamic = "force-dynamic";

export default function ToolPage({ params }: { params: { slug: string } }) {
  const manifest = getToolBySlug(params.slug);
  if (!manifest) notFound();

  const backendUrl = resolveBackendUrl(manifest);
  const vault: Record<string, string> = {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY || "",
    GITHUB_TOKEN: process.env.GITHUB_TOKEN || "",
    ADZUNA_APP_ID: process.env.ADZUNA_APP_ID || "",
    APOLLO_API_KEY: process.env.APOLLO_API_KEY || "",
    HUNTER_API_KEY: process.env.HUNTER_API_KEY || "",
    SAM_GOV_API_KEY: process.env.SAM_GOV_API_KEY || "",
  };

  return (
    <ToolProvider manifest={manifest} backendUrl={backendUrl} vault={vault}>
      <ModuleAccentShell moduleId={params.slug}>
        <ModulePageHeader
          title={manifest.name}
          description={manifest.tagline}
          moduleId={params.slug}
          category={manifest.category}
        />
        <ToolHost slug={params.slug} />
      </ModuleAccentShell>
    </ToolProvider>
  );
}
