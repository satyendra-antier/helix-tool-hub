"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  BarChart3,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  Menu,
  Plug,
  Settings,
  Shield,
  Users,
  Workflow,
} from "lucide-react";
import { useState } from "react";
import type { ToolManifest } from "@tool-hub/shared-types";
import { cn, Button, Sheet, SheetContent, SheetTrigger, getModuleTheme } from "@tool-hub/ui";

const OVERVIEW = [
  { href: "/dashboard", label: "Command Center", icon: LayoutDashboard },
  { href: "/studio", label: "Pipeline Studio", icon: Workflow },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

const PLATFORM = [
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];

const ADMIN = [
  { href: "/admin/users", label: "Users & Roles", icon: Users },
  { href: "/admin/system", label: "System Health", icon: Shield },
  { href: "/admin/audit", label: "Audit Log", icon: Shield },
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

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-4">
        <Link href="/dashboard" className="block" onClick={onNavigate}>
          <p className="text-sm font-semibold text-text-primary">Tool Hub</p>
          <p className="text-xs text-text-muted">Revenue Intelligence Engine</p>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        <div>
          <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Overview</p>
          <div className="space-y-0.5">
            {OVERVIEW.map((item) => (
              <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={onNavigate} />
            ))}
          </div>
        </div>

        <div>
          <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Intelligence</p>
          <div className="space-y-0.5">
            {tools.map((tool) => {
              const theme = getModuleTheme(tool.id);
              const active = isActive(tool.route);
              return (
                <Link
                  key={tool.id}
                  href={tool.route}
                  onClick={onNavigate}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-text-secondary hover:bg-surface-muted hover:text-text-primary"
                  )}
                >
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: theme.accent }} />
                  {tool.name}
                </Link>
              );
            })}
          </div>
        </div>

        <div>
          <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Platform</p>
          <div className="space-y-0.5">
            {PLATFORM.map((item) => (
              <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={onNavigate} />
            ))}
          </div>
        </div>

        {isAdmin ? (
          <div>
            <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Admin</p>
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
        Workspace <ChevronRight className="h-3 w-3" />
      </Link>
    </header>
  );
}
