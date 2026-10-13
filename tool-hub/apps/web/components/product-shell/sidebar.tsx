"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  BarChart3,
  Check,
  ChevronRight,
  Home,
  LogOut,
  Menu,
  Plug,
  Puzzle,
  ScrollText,
  Settings,
  Shield,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ToolManifest } from "@tool-hub/shared-types";
import { cn, Button, Sheet, SheetContent, SheetTrigger, getModuleTheme } from "@tool-hub/ui";
import { BRAND, EXTRAS, JOURNEY, getExtra, getStep, type FlywheelStatus } from "@/lib/journey";

const EXTRA_LINKS = [
  { href: "/studio", label: "Automation", icon: Workflow },
  { href: "/analytics", label: "Reports", icon: BarChart3 },
];

const SETUP = [
  { href: "/integrations", label: "Connections", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];

const ADMIN = [
  { href: "/admin/users", label: "Users & Roles", icon: Users },
  { href: "/admin/system", label: "System Health", icon: Shield },
  { href: "/admin/audit", label: "Audit Log", icon: ScrollText },
];

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  onClick,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-text-secondary hover:bg-surface-muted hover:text-text-primary"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">{children}</p>
  );
}

function useFlywheel(): FlywheelStatus | undefined {
  const [flywheel, setFlywheel] = useState<FlywheelStatus>();
  useEffect(() => {
    let cancelled = false;
    fetch("/api/hub/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d?.flywheel) setFlywheel(d.flywheel);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return flywheel;
}

function SidebarContent({
  tools,
  onNavigate,
}: {
  tools: ToolManifest[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const isAdmin = session?.user?.role === "admin";
  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");
  const flywheel = useFlywheel();

  const installed = new Set(tools.map((t) => t.id));
  const steps = JOURNEY.filter((s) => installed.has(s.id));
  const extraTools = [
    ...EXTRAS.filter((e) => installed.has(e.id)),
    ...tools
      .filter((t) => !getStep(t.id) && !getExtra(t.id))
      .map((t) => ({ id: t.id, name: t.name, icon: Puzzle, route: t.route, blurb: t.tagline })),
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-4">
        <Link href="/dashboard" className="flex items-center gap-2.5" onClick={onNavigate}>
          <span className="ai-gradient ai-glow flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold ai-text">{BRAND.name}</span>
            <span className="block text-xs text-text-muted truncate">{BRAND.tagline}</span>
          </span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        <div>
          <SectionLabel>Start here</SectionLabel>
          <NavLink href="/dashboard" label="Home" icon={Home} active={isActive("/dashboard")} onClick={onNavigate} />
        </div>

        <div>
          <SectionLabel>Your {steps.length} steps</SectionLabel>
          <ol className="space-y-0.5">
            {steps.map((step) => {
              const theme = getModuleTheme(step.id);
              const active = isActive(step.route);
              const done = flywheel?.[step.statusKey]?.ready;
              const Icon = step.icon;
              return (
                <li key={step.id}>
                  <Link
                    href={step.route}
                    onClick={onNavigate}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-text-secondary hover:bg-surface-muted hover:text-text-primary"
                    )}
                  >
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                      style={{ backgroundColor: done ? "var(--success)" : theme.accent }}
                      aria-label={done ? `Step ${step.step} done` : `Step ${step.step}`}
                    >
                      {done ? <Check className="h-3.5 w-3.5" /> : step.step}
                    </span>
                    <Icon className="h-4 w-4 shrink-0 opacity-70" />
                    <span className="truncate">{step.name}</span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </div>

        <div>
          <SectionLabel>Extras</SectionLabel>
          <div className="space-y-0.5">
            {extraTools.map((tool) => (
              <NavLink
                key={tool.id}
                href={tool.route}
                label={tool.name}
                icon={tool.icon}
                active={isActive(tool.route)}
                onClick={onNavigate}
              />
            ))}
            {EXTRA_LINKS.map((item) => (
              <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={onNavigate} />
            ))}
          </div>
        </div>

        <div>
          <SectionLabel>Setup</SectionLabel>
          <div className="space-y-0.5">
            {SETUP.map((item) => (
              <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={onNavigate} />
            ))}
          </div>
        </div>

        {isAdmin ? (
          <div>
            <SectionLabel>Admin</SectionLabel>
            <div className="space-y-0.5">
              {ADMIN.map((item) => (
                <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={onNavigate} />
              ))}
            </div>
          </div>
        ) : null}
      </nav>

      <div className="border-t border-border p-3">
        <div className="rounded-lg bg-surface-muted px-3 py-2 mb-2">
          <p className="text-xs font-medium text-text-primary truncate">{session?.user?.name}</p>
          <p className="text-[10px] text-text-muted truncate">{session?.user?.email}</p>
          <p className="text-[10px] text-text-muted capitalize mt-0.5">{session?.user?.role}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={() => {
            // Avoid NextAuth prefixing callback with NEXTAUTH_URL (often localhost in misconfigured deploys).
            void signOut({ redirect: false }).then(() => {
              window.location.assign("/login");
            });
          }}
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </Button>
      </div>
    </div>
  );
}

export function ProductSidebar({ tools }: { tools: ToolManifest[] }) {
  return (
    <aside className="hidden lg:flex w-60 shrink-0 border-r border-border bg-surface h-screen sticky top-0 flex-col">
      <SidebarContent tools={tools} />
    </aside>
  );
}

export function MobileSidebar({ tools }: { tools: ToolManifest[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="lg:hidden">
          <Menu className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SidebarContent tools={tools} onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}

export function ProductTopBar({ tools, title }: { tools: ToolManifest[]; title?: string }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface/95 backdrop-blur px-4 lg:px-6">
      <MobileSidebar tools={tools} />
      <div className="min-w-0 flex-1">
        {title ? <h1 className="text-sm font-semibold text-text-primary truncate">{title}</h1> : null}
      </div>
      <Link href="/dashboard" className="text-xs text-text-muted hover:text-text-primary hidden sm:flex items-center gap-1">
        Home <ChevronRight className="h-3 w-3" />
      </Link>
    </header>
  );
}
