import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@tool-hub/ui";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Tool Hub — Revenue Intelligence Engine",
  description: "Deterministic revenue operating system for technical services firms.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <ToastProvider>{children}</ToastProvider>
        </Providers>
      </body>
    </html>
  );
}
