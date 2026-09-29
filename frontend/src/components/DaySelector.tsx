import { MAX_LEAD_DAY } from "../lib/constants";

export function DaySelector({
  value,
  onChange,
}: {
  value: number;
  onChange: (d: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Forecast lead day">
      <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        Day
      </span>
      {Array.from({ length: MAX_LEAD_DAY }, (_, i) => i + 1).map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          aria-pressed={value === d}
          className={`h-8 w-8 rounded-md text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
            value === d
              ? "bg-sky-600 text-white shadow"
              : "bg-white text-slate-600 hover:bg-sky-50 border border-slate-200"
          }`}
        >
          {d}
        </button>
      ))}
    </div>
  );
}
