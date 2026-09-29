import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Api } from "../lib/api";
import type {
  AnalyticsError,
  Confidence,
  Explanation,
  Forecast,
  Region,
  TenDayResponse,
} from "../lib/types";
import { VariableSelector } from "../components/VariableSelector";
import { RiskBadge } from "../components/RiskBadge";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { InfoTooltip } from "../components/InfoTooltip";
import { ForecastVerificationChart } from "../components/ForecastVerificationChart";
import { VARIABLE_LABELS, VARIABLE_UNITS, fmtTime, pct } from "../lib/format";
import { useAppStore } from "../store";

export function RegionDetailsPage({ regionId }: { regionId?: string }) {
  const { selectedRegionId, setSelectedRegion, selectedVariable: variable, setSelectedVariable } =
    useAppStore();

  const [regions, setRegions] = useState<Region[]>([]);
  const [tenDay, setTenDay] = useState<TenDayResponse | null>(null);
  const [conf, setConf] = useState<Confidence | null>(null);
  const [expl, setExpl] = useState<Explanation | null>(null);
  const [hist, setHist] = useState<AnalyticsError | null>(null);
  const [fcsts, setFcsts] = useState<Forecast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const effectiveRegion = regionId ?? selectedRegionId ?? regions[0]?.region_id;

  useEffect(() => {
    Api.regions()
      .then(setRegions)
      .catch((e) => {
        setRegions([]);
        setError(e instanceof Error ? e.message : "Unable to load regions");
        setLoading(false);
      });
  }, []);

  const load = useCallback(async () => {
    if (!effectiveRegion) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [trend, c, h, f] = await Promise.all([
        Api.confidence10day(effectiveRegion, variable).catch(() => null),
        Api.confidence(effectiveRegion, 5, variable).catch(() => null),
        Api.analyticsError(effectiveRegion, variable, 5).catch(() => null),
        Api.forecast(effectiveRegion, undefined, variable).catch(() => []),
      ]);
      setTenDay(trend);
      setConf(c);
      setHist(h);
      setFcsts(f);
      setExpl(
        c?.prediction_id
          ? await Api.explanation(c.prediction_id).catch(() => null)
          : null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Region data unavailable");
    } finally {
      setLoading(false);
    }
  }, [effectiveRegion, variable]);

  useEffect(() => {
    load();
  }, [load]);

  const region = regions.find((r) => r.region_id === effectiveRegion);
  const chartData = tenDay?.days.map((d) => ({
    day: `D${d.lead_day}`,
    confidence: +(d.confidence * 100).toFixed(1),
    bust: +(d.bust_probability * 100).toFixed(1),
    error: d.expected_error,
  })) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            {region ? `${region.region_name}, ${region.state}` : "Region Details"}
          </h1>
          <p className="text-sm text-slate-500">
            {region
              ? `${region.latitude.toFixed(2)}°N, ${region.longitude.toFixed(2)}°E · elev ${region.elevation} m${region.coastal ? " · coastal" : ""}`
              : "Select a region"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Region
            <select
              value={effectiveRegion ?? ""}
              onChange={(e) => setSelectedRegion(e.target.value)}
              className="ml-2 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal"
            >
              {regions.map((r) => (
                <option key={r.region_id} value={r.region_id}>
                  {r.region_name}
                </option>
              ))}
            </select>
          </label>
          <VariableSelector value={variable} onChange={setSelectedVariable} />
        </div>
      </div>

      {loading && <LoadingCard label="Loading region details..." />}
      {error && <ErrorCard title="Region data unavailable" message={error} onRetry={load} />}

      {!loading && !error && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Current Reliability (Day 5)
              </h2>
              {conf ? (
                <>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-sm text-slate-500">Confidence</span>
                    <span className="text-lg font-bold">{pct(conf.confidence_score)}</span>
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-sm text-slate-500">Bust Probability</span>
                    <span className="text-lg font-bold">{pct(conf.bust_probability)}</span>
                  </div>
                  <div className="mt-1">
                    <RiskBadge level={conf.risk_level} showProbability={false} />
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-500">No prediction available.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Forecast — {VARIABLE_LABELS[variable]}
              </h2>
              <table className="w-full text-sm">
                <tbody>
                  {fcsts.slice(0, 5).map((f) => (
                    <tr key={`${f.lead_day}`} className="border-b border-slate-100 last:border-0">
                      <td className="py-1.5 text-slate-500">Day {f.lead_day}</td>
                      <td className="py-1.5 text-right font-semibold">
                        {f.value.toFixed(1)} {VARIABLE_UNITS[variable]}
                      </td>
                    </tr>
                  ))}
                  {fcsts.length === 0 && (
                    <tr>
                      <td className="py-1.5 text-slate-500">No forecast data.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {hist && (
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Historical Error (Day 5)
                </h2>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between items-center">
                    <InfoTooltip term="mae">
                      <span className="text-slate-500">MAE</span>
                    </InfoTooltip>
                    <span className="font-semibold">{hist.statistics.mae.toFixed(1)} {VARIABLE_UNITS[variable]}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <InfoTooltip term="rmse">
                      <span className="text-slate-500">RMSE</span>
                    </InfoTooltip>
                    <span className="font-semibold">{hist.statistics.rmse.toFixed(1)} {VARIABLE_UNITS[variable]}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <InfoTooltip term="bias">
                      <span className="text-slate-500">Bias</span>
                    </InfoTooltip>
                    <span className="font-semibold">{hist.statistics.bias.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Bust Rate</span>
                    <span className="font-semibold">{pct(hist.statistics.bust_rate)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Samples</span>
                    <span className="font-semibold">{hist.statistics.sample_count}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4 lg:col-span-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                10-Day Confidence Trend
              </h2>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} unit="%" />
                    <ReTooltip
                      formatter={(value, name) => [
                        `${value}%`,
                        name === "confidence" ? "Confidence" : "Bust Probability",
                      ]}
                    />
                    <Line type="monotone" dataKey="confidence" stroke="#0b8e75" strokeWidth={2} dot />
                    <Line type="monotone" dataKey="bust" stroke="#dc2626" strokeWidth={2} dot />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-8 text-center text-sm text-slate-500">
                  No 10-day prediction series is available for this region and variable yet.
                </p>
              )}
            </div>

            {effectiveRegion && (
              <ForecastVerificationChart
                regionId={effectiveRegion}
                variable={variable}
              />
            )}

            {expl && (
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  AI Explanation (Day 5 · {VARIABLE_LABELS[variable]})
                </h2>
                <p className="text-sm text-slate-600">{expl.summary}</p>
                <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
                  {expl.explanation.map((f) => (
                    <li key={f.feature} className="text-sm text-slate-700">
                      <span className={`mr-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold text-white ${
                        f.impact === "HIGH" ? "bg-red-500" : f.impact === "MEDIUM" ? "bg-amber-500" : "bg-slate-400"
                      }`}>
                        {f.impact}
                      </span>
                      {f.label}
                    </li>
                  ))}
                </ul>
                <div className="mt-2 text-[11px] text-slate-400">
                  Prediction {expl.prediction_id} · Model {expl.model_version}
                </div>
              </div>
            )}

            {tenDay && (
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Forecast Run Details
                </h2>
                <div className="text-xs text-slate-500">Run: {fmtTime(tenDay.forecast_run)}</div>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                        <th className="py-1.5 pr-3">Day</th>
                        <th className="py-1.5 pr-3">Forecast</th>
                        <th className="py-1.5 pr-3">Bust Prob.</th>
                        <th className="py-1.5 pr-3">Confidence</th>
                        <th className="py-1.5">Expected Err</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tenDay.days.map((d) => (
                        <tr key={d.lead_day} className="border-b border-slate-100">
                          <td className="py-1.5 pr-3 font-medium">D{d.lead_day}</td>
                          <td className="py-1.5 pr-3">{d.forecast_value?.toFixed(1) ?? "—"} {VARIABLE_UNITS[variable]}</td>
                          <td className="py-1.5 pr-3">{pct(d.bust_probability)}</td>
                          <td className="py-1.5 pr-3">{pct(d.confidence)}</td>
                          <td className="py-1.5">{d.expected_error.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
