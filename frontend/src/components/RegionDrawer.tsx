import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { Api } from "../lib/api";
import { VARIABLE_LABELS, VARIABLE_UNITS, pct, fmtTime } from "../lib/format";
import type {
  AnalyticsError,
  Confidence,
  Explanation,
  MapRegionPoint,
  Variable,
} from "../lib/types";
import { RiskBadge } from "./RiskBadge";
import { ErrorCard, LoadingCard } from "./LoadingError";

export function RegionDrawer({
  region,
  variable,
  leadDay,
  onClose,
  onOpenDetails,
}: {
  region: MapRegionPoint;
  variable: Variable;
  leadDay: number;
  onClose: () => void;
  onOpenDetails: (regionId: string) => void;
}) {
  const [confidence, setConfidence] = useState<Confidence | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [history, setHistory] = useState<AnalyticsError | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const conf = await Api.confidence(region.region_id, leadDay, variable);
      setConfidence(conf);
      const [expl, hist] = await Promise.all([
        conf.prediction_id
          ? Api.explanation(conf.prediction_id)
          : Promise.resolve(null),
        Api.analyticsError(region.region_id, variable, leadDay).catch(() => null),
      ]);
      setExplanation(expl);
      setHistory(hist);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load region data");
    } finally {
      setLoading(false);
    }
  }, [region.region_id, leadDay, variable]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div
      className="fixed inset-0 z-[1000] flex justify-end bg-black/30"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${region.region_name} details`}
    >
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {region.region_name}
            </h2>
            <div className="text-sm text-slate-500">
              {region.state} · {VARIABLE_LABELS[variable]} · Day {leadDay}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={20} />
          </button>
        </div>

        {loading && <LoadingCard label="Loading region reliability..." />}
        {error && <ErrorCard title="Unable to load region data" message={error} onRetry={load} />}

        {!loading && !error && confidence && (
          <>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="text-2xl font-bold text-slate-900">
                  {pct(confidence.bust_probability)}
                </div>
                <div className="text-[11px] uppercase tracking-wide text-slate-500">
                  Bust Probability
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="text-2xl font-bold text-slate-900">
                  {pct(confidence.confidence_score)}
                </div>
                <div className="text-[11px] uppercase tracking-wide text-slate-500">
                  Confidence
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3 flex flex-col items-center justify-center">
                <RiskBadge level={confidence.risk_level} showProbability={false} />
                <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">
                  Risk
                </div>
              </div>
            </div>

            <div className="mt-3 rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex justify-between py-0.5">
                <span className="text-slate-500">Expected Error</span>
                <span className="font-semibold">
                  {confidence.expected_error.toFixed(1)}{" "}
                  {VARIABLE_UNITS[variable]}
                </span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-slate-500">Forecast Value</span>
                <span className="font-semibold">
                  {confidence.forecast_value?.toFixed(1) ?? "—"}{" "}
                  {VARIABLE_UNITS[variable]}
                </span>
              </div>
              {history && (
                <>
                  <div className="flex justify-between py-0.5">
                    <span className="text-slate-500">Historical MAE</span>
                    <span className="font-semibold">
                      {history.statistics.mae.toFixed(1)} {VARIABLE_UNITS[variable]}
                    </span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <span className="text-slate-500">Historical Bust Rate</span>
                    <span className="font-semibold">
                      {pct(history.statistics.bust_rate)}
                    </span>
                  </div>
                </>
              )}
              <div className="flex justify-between py-0.5">
                <span className="text-slate-500">Model</span>
                <span className="font-mono text-xs font-semibold">
                  {confidence.model_version ?? "—"}
                </span>
              </div>
            </div>

            {explanation && (
              <div className="mt-3 rounded-lg border border-slate-200 p-3">
                <div className="text-sm font-semibold text-slate-800">
                  Why this prediction?
                </div>
                <p className="mt-1 text-sm text-slate-600">{explanation.summary}</p>
                <ul className="mt-2 space-y-1.5">
                  {explanation.explanation.map((f) => (
                    <li key={f.feature} className="text-sm">
                      <span
                        className={`mr-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold text-white ${
                          f.impact === "HIGH"
                            ? "bg-red-500"
                            : f.impact === "MEDIUM"
                              ? "bg-amber-500"
                              : "bg-slate-400"
                        }`}
                      >
                        {f.impact}
                      </span>
                      {f.label}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-3 text-[11px] text-slate-400">
              Forecast run: {fmtTime(confidence.forecast_run)}
            </div>

            <button
              onClick={() => onOpenDetails(region.region_id)}
              className="mt-4 w-full rounded-md bg-sky-600 px-3 py-2 text-sm font-semibold text-white hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
            >
              View Region Details
            </button>
          </>
        )}
      </div>
    </div>
  );
}
