export function KpiCard({
  label,
  value,
  sub,
  accent,
  onClick,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm ${
        onClick ? "hover:border-sky-300 hover:shadow transition" : "cursor-default"
      }`}
    >
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-3xl font-bold ${accent ?? "text-slate-900"}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </button>
  );
}
