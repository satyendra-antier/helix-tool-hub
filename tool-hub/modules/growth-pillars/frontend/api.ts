"use client";

import { useMemo } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";

export type Api = {
  get: <T>(path: string) => Promise<T>;
  post: <T>(path: string, body?: unknown) => Promise<T>;
  patch: <T>(path: string, body?: unknown) => Promise<T>;
  del: <T>(path: string) => Promise<T>;
  pollJob: (jobId: string, onTick?: (job: Job) => void) => Promise<Job>;
};

export type Job = {
  id: string;
  job_type: string;
  status: "queued" | "running" | "done" | "failed";
  progress: Record<string, unknown>;
  result: Record<string, unknown>;
  error?: string | null;
};

async function request<T>(base: string, method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${method} ${path} failed: ${detail}`);
  }
  return (await res.json()) as T;
}

export function useApi(): Api {
  const { backendUrl } = useToolContext();
  return useMemo(() => {
    const get = <T,>(p: string) => request<T>(backendUrl, "GET", p);
    return {
      get,
      post: <T,>(p: string, b?: unknown) => request<T>(backendUrl, "POST", p, b ?? {}),
      patch: <T,>(p: string, b?: unknown) => request<T>(backendUrl, "PATCH", p, b ?? {}),
      del: <T,>(p: string) => request<T>(backendUrl, "DELETE", p),
      pollJob: async (jobId: string, onTick?: (job: Job) => void) => {
        for (;;) {
          const job = await get<Job>(`/jobs/${jobId}`);
          onTick?.(job);
          if (job.status === "done" || job.status === "failed") return job;
          await new Promise((r) => setTimeout(r, 2500));
        }
      },
    };
  }, [backendUrl]);
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}
