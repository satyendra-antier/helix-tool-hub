export function FlywheelDiagram({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 720 280" className={className} aria-label="Revenue intelligence flywheel">
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#64748b" />
        </marker>
      </defs>
      <rect x="20" y="90" width="150" height="64" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
      <text x="95" y="118" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">Market Depth</text>
      <text x="95" y="136" textAnchor="middle" className="fill-slate-500 text-[11px]">12 domains · 5 signals</text>

      <rect x="220" y="90" width="150" height="64" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
      <text x="295" y="118" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">Build Readiness</text>
      <text x="295" y="136" textAnchor="middle" className="fill-slate-500 text-[11px]">GO / NO_GO + citations</text>

      <rect x="420" y="90" width="150" height="64" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
      <text x="495" y="118" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">Lead Intelligence</text>
      <text x="495" y="136" textAnchor="middle" className="fill-slate-500 text-[11px]">Demand + future pipeline</text>

      <rect x="220" y="200" width="150" height="56" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
      <text x="295" y="232" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">Video Scraper</text>

      <line x1="170" y1="122" x2="220" y2="122" stroke="#64748b" markerEnd="url(#arrow)" />
      <line x1="370" y1="122" x2="420" y2="122" stroke="#64748b" markerEnd="url(#arrow)" />
      <line x1="295" y1="154" x2="295" y2="200" stroke="#64748b" markerEnd="url(#arrow)" />
      <line x1="370" y1="228" x2="420" y2="140" stroke="#94a3b8" strokeDasharray="4 3" markerEnd="url(#arrow)" />

      <text x="600" y="124" className="fill-slate-400 text-[11px]">Weekly refresh</text>
      <path d="M560 100 Q640 60 680 100" fill="none" stroke="#cbd5e1" strokeWidth="1.5" markerEnd="url(#arrow)" />
    </svg>
  );
}
