import { MarketingNav } from "@/components/marketing/nav";
import Link from "next/link";
import { DEFAULT_WEIGHTS } from "@tool-hub/shared-types";

export default function MethodologyPage() {
  const weights = Object.entries(DEFAULT_WEIGHTS);

  return (
    <>
      <MarketingNav />
      <article className="max-w-3xl mx-auto px-4 py-16 prose prose-slate">
        <h1 className="text-3xl font-semibold text-text-primary">Methodology</h1>
        <p className="text-text-secondary leading-relaxed mt-4">
          Tool Hub combines algorithmic market scoring with company-specific retrieval-augmented verdicts.
          Outputs are designed for board reporting and BD operations — not open-ended chat.
        </p>

        <h2 className="text-xl font-semibold mt-10 text-text-primary">Market Depth scoring</h2>
        <p className="text-text-secondary mt-2">
          Each domain receives a composite score (0–100) from min-max normalized signals. Default weights:
        </p>
        <ul className="mt-4 space-y-2 text-sm text-text-secondary">
          {weights.map(([k, v]) => (
            <li key={k}>
              <span className="font-mono text-text-primary">{k}</span> — {(v * 100).toFixed(0)}%
            </li>
          ))}
        </ul>

        <h2 className="text-xl font-semibold mt-10 text-text-primary">Build Readiness verdicts</h2>
        <p className="text-text-secondary mt-2">
          For each domain, opportunity score combines market heat with indexed capability depth from your website and videos.
          Verdicts: GO, CONDITIONAL, NO_GO — each with citations from your own content.
        </p>

        <h2 className="text-xl font-semibold mt-10 text-text-primary">Lead orientation</h2>
        <p className="text-text-secondary mt-2">
          Demand-oriented leads align hot markets with proven depth. Future-oriented leads flag growth domains where capability can be built.
        </p>

        <p className="mt-12">
          <Link href="/login" className="text-primary font-medium hover:underline">
            Sign in to run the flywheel →
          </Link>
        </p>
      </article>
    </>
  );
}
