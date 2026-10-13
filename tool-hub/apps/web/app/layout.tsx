import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@tool-hub/ui";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "LeadGen AI — Find and win leads with AI",
  description: "Find demand, check fit, find leads and win them, in four simple AI-powered steps.",
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
