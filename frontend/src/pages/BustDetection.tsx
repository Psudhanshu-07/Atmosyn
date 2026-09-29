import { useEffect, useState } from "react";
import { Info, Database } from "lucide-react";
import { Api } from "../lib/api";
import type {
  AnalyticsError,
  Confidence,
  Explanation,
  Region,
} from "../lib/types";
import { DaySelector } from "../components/DaySelector";
import { VariableSelector } from "../components/VariableSelector";
import { RiskBadge } from "../components/RiskBadge";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { InfoTooltip } from "../components/InfoTooltip";
import { VARIABLE_UNITS, fmtTime, pct } from "../lib/format";
import { useAppStore } from "../store";

export function BustDetectionPage() {
  const {
    selectedRegionId,
    setSelectedRegion,
    selectedLeadDay: leadDay,
    setSelectedLeadDay,
    selectedVariable: variable,
    setSelectedVariable,
    userMode,
  } = useAppStore();

  const [regions, setRegions] = useState<Region[]>([]);
  const [confidence, setConfidence] = useState<Confidence | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [history, setHistory] = useState<AnalyticsError | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Api.regions().then(setRegions).catch(() => setRegions([]));
  }, []);

  const effectiveRegion = selectedRegionId ?? regions[0]?.region_id ?? null;

  useEffect(() => {
    if (!effectiveRegion) return;
    setLoading(true);
    setError(null);
    Promise.all([
      Api.confidence(effectiveRegion, leadDay, variable),
      Api.analyticsError(effectiveRegion, variable, leadDay).catch(() => null),
    ])
      .then(async ([conf, hist]) => {
        setConfidence(conf);
        setHistory(hist);
        setExplanation(
          conf.prediction_id ? await Api.explanation(conf.prediction_id) : null,
        );
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Prediction unavailable"),
      )
      .finally(() => setLoading(false));
  }, [effectiveRegion, leadDay, variable]);

  const maxShap = explanation
    ? Math.max(...explanation.explanation.map((f) => f.shap_value), 0.001)
    : 1;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">AI Forecast Bust Detection</h1>
        <p className="text-sm text-slate-500">
          Estimated probability of a significant numerical forecast error (NWP error exceeding tolerance threshold)
        </p>
      </div>

      {/* Distinction Banner: Weather Probability vs Bust Probability (Master Prompt Requirement B) */}
      <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3.5 text-xs text-amber-950">
        <div className="flex items-start gap-2">
          <Info size={16} className="mt-0.5 text-amber-700 shrink-0" />
          <div className="space-y-1">
            <span className="font-bold">Important Distinction: Weather Event Probability vs. Forecast Bust Probability</span>
            <p className="leading-relaxed text-amber-900">
              A <b>Bust Probability of {confidence ? pct(confidence.bust_probability) : "75%"}</b> does <b>NOT</b> mean a {confidence ? pct(confidence.bust_probability) : "75%"} chance of rain or weather occurring. It represents an AI estimate that the numerical weather forecast itself will experience a significant error relative to the defined threshold (e.g. error &gt;20–60 mm). It is a measure of forecast reliability, not a severe weather warning.
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Region
          <select
            value={effectiveRegion ?? ""}
            onChange={(e) => setSelectedRegion(e.target.value)}
            className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-800"
          >
            {regions.map((r) => (
              <option key={r.region_id} value={r.region_id}>
                {r.region_name}, {r.state}
              </option>
            ))}
          </select>
        </label>
        <VariableSelector value={variable} onChange={setSelectedVariable} />
        <div>
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Lead Day
          </span>
          <div className="mt-1">
            <DaySelector value={leadDay} onChange={setSelectedLeadDay} />
          </div>
        </div>
      </div>

      {loading && <LoadingCard label="Evaluating AI bust detection models..." />}
      {error && (
        <ErrorCard
          title="AI confidence unavailable"
          message={error}
          onRetry={() => setSelectedLeadDay(leadDay)}
        />
      )}

      {!loading && !error && confidence && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Main Bust Detection KPI Card */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 text-center shadow-xs">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 flex items-center justify-center gap-1">
              <InfoTooltip term="bust_probability" mode={userMode}>
                <span>Calibrated Bust Probability</span>
              </InfoTooltip>
            </div>
            <div className="mt-2 text-6xl font-bold tracking-tight text-slate-900">
              {pct(confidence.bust_probability)}
            </div>
            <div className="mt-2 flex justify-center">
              <RiskBadge level={confidence.risk_level} showProbability={false} size="lg" />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
                <div className="font-bold text-slate-900">
                  {pct(confidence.confidence_score)}
                </div>
                <div className="text-xs text-slate-500 flex items-center justify-center gap-1">
                  <InfoTooltip term="confidence" mode={userMode}>
                    <span>AI Reliability</span>
                  </InfoTooltip>
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
                <div className="font-bold text-slate-900">
                  ±{confidence.expected_error.toFixed(1)} {VARIABLE_UNITS[variable]}
                </div>
                <div className="text-xs text-slate-500 flex items-center justify-center gap-1">
                  <InfoTooltip term="forecast_error" mode={userMode}>
                    <span>Expected Error</span>
                  </InfoTooltip>
                </div>
              </div>
            </div>

            {/* Data & Model Provenance Details (Master Prompt §20) */}
            <div className="mt-4 rounded-lg bg-slate-50/80 p-3 text-left border border-slate-100 text-xs space-y-1">
              <div className="font-semibold text-slate-700 flex items-center gap-1 mb-1">
                <Database size={13} className="text-sky-600" />
                Data & Model Details
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] text-slate-600">
                <div>Forecast Source: <span className="font-medium text-slate-800">NOAA/NCEP GFS 0.25°</span></div>
                <div>Verification: <span className="font-medium text-slate-800">NOAA NCEI Synoptic</span></div>
                <div>Model: <span className="font-medium text-slate-800">XGBoost (Isotonic Calibrated)</span></div>
                <div>Version: <span className="font-mono text-slate-800">{confidence.model_version}</span></div>
                <div>Run Time: <span className="text-slate-800">{fmtTime(confidence.forecast_run)}</span></div>
                <div>Valid Time: <span className="text-slate-800">{fmtTime(confidence.valid_time)}</span></div>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            {/* SHAP Contributing Factors (Master Prompt §17) */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Top Contributing Factors (SHAP Attribution)
              </h2>
              {explanation && explanation.explanation.length > 0 ? (
                <div className="space-y-2.5">
                  {explanation.explanation.map((f) => (
                    <div key={f.feature}>
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-slate-800">{f.label}</span>
                        <span className="text-slate-600 font-medium">
                          {f.impact} impact · +{f.shap_value.toFixed(2)}
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded bg-slate-100">
                        <div
                          className="h-full rounded bg-orange-500 transition-all"
                          style={{ width: `${(f.shap_value / maxShap) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                  <div className="mt-3 rounded-md bg-slate-50 p-2.5 text-xs text-slate-700 border border-slate-100">
                    <p className="leading-relaxed">
                      <b>Summary:</b> {explanation.summary}
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  Explanation unavailable for this prediction.
                </p>
              )}
            </div>

            {/* Historical Error Performance */}
            {history && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Historical Baseline (Lead Day {leadDay})
                </h2>
                {history.statistics.sample_count < 5 ? (
                  <div className="rounded-md bg-amber-50 p-3 text-xs text-amber-800">
                    Historical estimate unavailable: insufficient comparable cases (n = {history.statistics.sample_count}).
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-2 text-center text-sm">
                    <div className="rounded bg-slate-50 p-2 border border-slate-100">
                      <div className="font-bold text-slate-800">{history.statistics.mae.toFixed(1)}</div>
                      <div className="text-[11px] text-slate-500">MAE ({VARIABLE_UNITS[variable]})</div>
                    </div>
                    <div className="rounded bg-slate-50 p-2 border border-slate-100">
                      <div className="font-bold text-slate-800">{history.statistics.rmse.toFixed(1)}</div>
                      <div className="text-[11px] text-slate-500">RMSE</div>
                    </div>
                    <div className="rounded bg-slate-50 p-2 border border-slate-100">
                      <div className="font-bold text-slate-800">{pct(history.statistics.bust_rate)}</div>
                      <div className="text-[11px] text-slate-500">Bust Rate</div>
                    </div>
                    <div className="rounded bg-slate-50 p-2 border border-slate-100">
                      <div className="font-bold text-slate-800">{history.statistics.sample_count}</div>
                      <div className="text-[11px] text-slate-500">Verified Cases</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
