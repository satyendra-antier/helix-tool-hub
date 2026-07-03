"use client";

import React, { createContext, useContext, useMemo } from "react";
import type { ToolManifest } from "./index";

type VaultKeys = Record<string, string>;

interface ToolContextValue {
  manifest: ToolManifest;
  backendUrl: string;
  vault: VaultKeys;
}

const ToolContext = createContext<ToolContextValue | null>(null);

export function ToolProvider({
  manifest,
  backendUrl,
  vault,
  children,
}: {
  manifest: ToolManifest;
  backendUrl: string;
  vault: VaultKeys;
  children: React.ReactNode;
}) {
  const value = useMemo(
    () => ({ manifest, backendUrl, vault }),
    [manifest, backendUrl, vault]
  );
  return <ToolContext.Provider value={value}>{children}</ToolContext.Provider>;
}

export function useToolContext() {
  const ctx = useContext(ToolContext);
  if (!ctx) throw new Error("useToolContext must be used within ToolProvider");
  return ctx;
}
