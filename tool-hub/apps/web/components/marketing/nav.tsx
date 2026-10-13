import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@tool-hub/ui";
import { BRAND } from "@/lib/journey";

export function MarketingNav() {
  return (
    <header className="border-b border-border bg-surface sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold">
          <span className="ai-gradient flex h-7 w-7 items-center justify-center rounded-lg text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="ai-text">{BRAND.name}</span>
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
            <Link href="/login">Get started</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
