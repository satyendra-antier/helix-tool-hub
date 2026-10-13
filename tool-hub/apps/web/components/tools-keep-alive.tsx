"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import type { ToolManifest } from "@tool-hub/shared-types";
import { ToolProvider } from "@/lib/tool-context";
import { ToolHost } from "@/components/tool-host";
import { ModuleAccentShell, ModulePageHeader, ModuleStepFooter } from "@/components/module-page-header";

type Props = {
  tools: ToolManifest[];
  backends: Record<string, string>;
  vault: Record<string, string>;
};

function slugFromPath(pathname: string): string | null {
  const match = pathname.match(/\/tools\/([^/]+)/);
  return match?.[1] ?? null;
}

/**
 * Keeps visited tool panels mounted (hidden) so long-running UIs
 * like Video Scraper retain in-memory progress when switching tools.
 */
export function ToolsKeepAlive({ tools, backends, vault }: Props) {
  const pathname = usePathname();
  const activeSlug = slugFromPath(pathname);
  const byId = useMemo(
    () => Object.fromEntries(tools.map((t) => [t.id, t])),
    [tools]
  );

  const [mounted, setMounted] = useState<string[]>(() =>
    activeSlug && byId[activeSlug] ? [activeSlug] : []
  );

  useEffect(() => {
    if (!activeSlug || !byId[activeSlug]) return;
    setMounted((prev) => (prev.includes(activeSlug) ? prev : [...prev, activeSlug]));
  }, [activeSlug, byId]);

  if (!activeSlug) return null;

  return (
    <>
      {mounted.map((id) => {
        const manifest = byId[id];
        if (!manifest) return null;
        const isActive = id === activeSlug;
        return (
          <div
            key={id}
            className={isActive ? "block" : "hidden"}
            aria-hidden={!isActive}
            data-tool-panel={id}
          >
            <ToolProvider
              manifest={manifest}
              backendUrl={backends[id] || ""}
              vault={vault}
            >
              <ModuleAccentShell moduleId={id}>
                <ModulePageHeader
                  title={manifest.name}
                  description={manifest.tagline}
                  moduleId={id}
                  category={manifest.category}
                />
                <ToolHost slug={id} />
                <ModuleStepFooter moduleId={id} />
              </ModuleAccentShell>
            </ToolProvider>
          </div>
        );
      })}
    </>
  );
}
