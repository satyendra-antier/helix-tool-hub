const STEPS = [
  { x: 15, title: "1 · Find Demand", sub: "Where buyers spend", color: "#2563eb" },
  { x: 195, title: "2 · Check Fit", sub: "GO / maybe / no", color: "#0d9488" },
  { x: 375, title: "3 · Find Leads", sub: "Scored companies", color: "#7c3aed" },
  { x: 555, title: "4 · Win Leads", sub: "Warm paths + coach", color: "#c026d3" },
];

export function FlywheelDiagram({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 720 280" className={className} aria-label="LeadGen AI four-step flow">
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#64748b" />
        </marker>
      </defs>
      {STEPS.map((s) => (
        <g key={s.title}>
          <rect x={s.x} y="90" width="150" height="64" rx="10" fill="#ffffff" stroke={s.color} strokeWidth="1.5" />
          <rect x={s.x} y="90" width="150" height="5" rx="2" fill={s.color} />
          <text x={s.x + 75} y="120" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">
            {s.title}
          </text>
          <text x={s.x + 75} y="138" textAnchor="middle" className="fill-slate-500 text-[11px]">
            {s.sub}
          </text>
        </g>
      ))}
      {[165, 345, 525].map((x) => (
        <line key={x} x1={x} y1="122" x2={x + 30} y2="122" stroke="#64748b" markerEnd="url(#arrow)" />
      ))}

      <rect x="195" y="200" width="150" height="56" rx="10" fill="#fffbeb" stroke="#fde68a" />
      <text x="270" y="226" textAnchor="middle" className="fill-slate-900 text-[13px] font-semibold">Proof Library</text>
      <text x="270" y="243" textAnchor="middle" className="fill-slate-500 text-[11px]">Demo videos as proof</text>
      <line x1="270" y1="200" x2="270" y2="154" stroke="#94a3b8" strokeDasharray="4 3" markerEnd="url(#arrow)" />

      <text x="360" y="50" textAnchor="middle" className="fill-slate-400 text-[11px]">
        Run all four with one click, or step by step
      </text>
    </svg>
  );
}
