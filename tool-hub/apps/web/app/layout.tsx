import type { Metadata } from "next";
import "./globals.css";
import { ShellNav } from "@/components/shell-nav";

export const metadata: Metadata = {
  title: "Tool Hub",
  description: "One launcher. Every tool plugs into the same registry.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ShellNav />
        <main>{children}</main>
      </body>
    </html>
  );
}
