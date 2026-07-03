import Link from "next/link";
import { loadToolRegistry } from "@/lib/registry";

export function ShellNav() {
  const tools = loadToolRegistry();

  return (
    <nav className="border-b border-border px-6 py-3 flex items-center justify-between bg-panel/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="flex items-center gap-6">
        <Link href="/" className="font-display font-bold text-lg">
          Tool<span className="text-accent-a">Hub</span>
        </Link>
        <div className="hidden md:flex items-center gap-1">
          {tools.map((tool) => (
            <Link
              key={tool.id}
              href={tool.route}
              className="font-mono text-xs text-text-secondary hover:text-text-primary px-3 py-1.5 rounded hover:bg-panel-raised transition-colors"
            >
              {tool.name}
            </Link>
          ))}
        </div>
      </div>
      <Link
        href="/settings"
        className="font-mono text-xs text-text-dim hover:text-text-secondary border border-border px-3 py-1.5 rounded"
      >
        vault / settings
      </Link>
    </nav>
  );
}
