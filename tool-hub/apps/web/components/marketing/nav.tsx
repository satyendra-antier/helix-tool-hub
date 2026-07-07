import Link from "next/link";
import { Button } from "@tool-hub/ui";

export function MarketingNav() {
  return (
    <header className="border-b border-border bg-surface sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="text-sm font-semibold text-text-primary">
          Tool Hub
        </Link>
        <nav className="hidden sm:flex items-center gap-6 text-sm text-text-secondary">
          <Link href="/#product" className="hover:text-text-primary">Product</Link>
          <Link href="/methodology" className="hover:text-text-primary">Methodology</Link>
          <Link href="/#compare" className="hover:text-text-primary">Why not agents</Link>
        </nav>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button size="sm" asChild>
            <Link href="/login">Open platform</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
