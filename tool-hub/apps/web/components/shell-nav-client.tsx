"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, Settings, LayoutGrid } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Button,
  cn,
} from "@tool-hub/ui";

export type NavTool = { id: string; name: string; route: string };

export function ShellNavClient({ tools }: { tools: NavTool[] }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const linkClass = (href: string) =>
    cn(
      "text-sm font-medium px-3 py-2 rounded-lg transition-colors",
      (href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`))
        ? "bg-primary/10 text-primary"
        : "text-text-secondary hover:text-text-primary hover:bg-surface-muted"
    );

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-surface/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-6 min-w-0">
          <Link href="/" className="flex items-center gap-2 shrink-0 font-semibold text-text-primary">
            <LayoutGrid className="h-5 w-5 text-primary" />
            <span>Tool Hub</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            <Link href="/dashboard" className={linkClass("/dashboard")}>
              Workspace
            </Link>
            {tools.map((tool) => (
              <Link key={tool.id} href={tool.route} className={linkClass(tool.route)}>
                {tool.name}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-2">
          <Link href="/settings" className={cn(linkClass("/settings"), "hidden sm:inline-flex items-center gap-1.5")}>
            <Settings className="h-4 w-4" />
            Settings
          </Link>

          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="md:hidden" aria-label="Open menu">
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="max-w-xs">
              <SheetHeader>
                <SheetTitle>Modules</SheetTitle>
              </SheetHeader>
              <nav className="flex flex-col gap-1 mt-4">
                <Link href="/" className={linkClass("/")} onClick={() => setMobileOpen(false)}>
                  Home
                </Link>
                <Link href="/dashboard" className={linkClass("/dashboard")} onClick={() => setMobileOpen(false)}>
                  Workspace
                </Link>
                {tools.map((tool) => (
                  <Link
                    key={tool.id}
                    href={tool.route}
                    className={linkClass(tool.route)}
                    onClick={() => setMobileOpen(false)}
                  >
                    {tool.name}
                  </Link>
                ))}
                <Link
                  href="/settings"
                  className={linkClass("/settings")}
                  onClick={() => setMobileOpen(false)}
                >
                  Settings
                </Link>
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
