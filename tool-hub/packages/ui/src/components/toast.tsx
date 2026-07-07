"use client";

import * as React from "react";
import { cn } from "../lib/utils";

type Toast = { id: number; message: string; variant?: "default" | "success" };

const ToastContext = React.createContext<{
  toast: (message: string, variant?: "default" | "success") => void;
} | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const toast = React.useCallback((message: string, variant: "default" | "success" = "default") => {
    const id = Date.now();
    setToasts((t) => [...t, { id, message, variant }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "rounded-lg border px-4 py-2 text-sm shadow-lg pointer-events-auto",
              t.variant === "success"
                ? "border-success/30 bg-surface text-success"
                : "border-border bg-surface text-text-primary"
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
