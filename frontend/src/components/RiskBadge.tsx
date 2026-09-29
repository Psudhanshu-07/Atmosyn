import { RISK_BG, pct, riskLabel } from "../lib/format";
import type { RiskLevel } from "../lib/types";

export function RiskBadge({
  level,
  probability,
  showProbability = true,
  size = "md",
}: {
  level: RiskLevel | undefined | null;
  probability?: number;
  showProbability?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const key = level ?? "NA";
  const sizeCls =
    size === "lg"
      ? "px-3 py-1.5 text-base"
      : size === "sm"
        ? "px-1.5 py-0.5 text-[10px]"
        : "px-2 py-0.5 text-xs";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-flex items-center gap-1 rounded font-semibold text-white uppercase tracking-wide ${RISK_BG[key]} ${sizeCls}`}
      >
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 rounded-full bg-white/80"
        />
        {riskLabel(level)}
      </span>
      {showProbability && probability != null && (
        <span className="font-semibold text-slate-700">{pct(probability)}</span>
      )}
    </span>
  );
}
