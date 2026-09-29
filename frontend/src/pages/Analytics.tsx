import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
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
  Region,
  TenDayResponse,
  TrendPoint,
} from "../lib/types";
import { VariableSelector } from "../components/VariableSelector";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { pct } from "../lib/format";
import { useAppStore } from "../store";

export function AnalyticsPage() {
  const { selectedVariable: variable, setSelectedVariable } = useAppStore();
  const [regions, setRegions] = useState<Region[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | undefined>(undefined);
  const [byLead, setByLead] = useState<TenDayResponse | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [stats, setStats] = useState<AnalyticsError | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Api.regions().then(setRegions).catch(() => setRegions([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Use Mumbai as the reference region for lead-day curves; regional
      // table below covers all regions from one trends call.
      const [lead, tr, st] = await Promise.all([
        Api.confidence10day("MH_MUM", variable).catch(() => null),
        Api.analyticsTrends(selectedRegion, variable).catch(() => []),
        selectedRegion
          ? Api.analyticsError(selectedRegion, variable).catch(() => null)
          : Promise.resolve(null),
      ]);
      setByLead(lead);
      setTrend(tr);
      setStats(st);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analytics unavailable");
    } finally {
      setLoading(false);
    }
  }, [selectedRegion, variable]);

  useEffect(() => {
    load();
  }, [load]);

  // Bust-rate curve by lead day uses expected error + risk from 10-day API
  const bustByLead = byLead?.days.map((d) => ({
    day: `D${d.lead_day}`,
    bust: +(d.bust_probability * 100).toFixed(1),
  })) ?? [];

  const maeByLead = byLead?.days.map((d) => ({
    day: `D${d.lead_day}`,
    mae: +d.expected_error.toFixed(1),
  })) ?? [];

  const trendData = trend.map((t) => ({
    month: t.date.slice(0, 7),
    mae: t.mae,
    bust: +(t.bust_rate * 100).toFixed(1),
  }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Analytics</h1>
          <p className="text-sm text-slate-500">Historical forecast-error behaviour</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Region
            <select
              value={selectedRegion ?? ""}
              onChange={(e) => setSelectedRegion(e.target.value || undefined)}
              className="ml-2 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal"
            >
              <option value="">All regions</option>
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

      {error && <ErrorCard title="Analytics unavailable" message={error} onRetry={load} />}
      {loading && <LoadingCard label="Loading analytics..." />}

      {!loading && !error && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Expected Error by Lead Day (Mumbai)
              </h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={maeByLead} margin={{ top: 5, right: 10, left: -15 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <ReTooltip />
                  <Bar dataKey="mae" fill="#0284c7" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Bust Probability by Lead Day (Mumbai)
              </h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={bustByLead} margin={{ top: 5, right: 10, left: -15 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} unit="%" />
                  <ReTooltip />
                  <Bar dataKey="bust" fill="#f97316" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Monthly Error Trend
              </h2>
              {trendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={trendData} margin={{ top: 5, right: 10, left: -15 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="l" tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 12 }} unit="%" />
                    <ReTooltip />
                    <Line yAxisId="l" type="monotone" dataKey="mae" name="MAE" stroke="#0284c7" strokeWidth={2} dot={false} />
                    <Line yAxisId="r" type="monotone" dataKey="bust" name="Bust %" stroke="#dc2626" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-slate-500">No trend data for this filter.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                {selectedRegion ? "Regional Error Statistics" : "Select a Region for Detailed Statistics"}
              </h2>
              {stats ? (
                <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{stats.statistics.mae.toFixed(1)}</div>
                    <div className="text-xs text-slate-500">MAE</div>
                  </div>
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{stats.statistics.rmse.toFixed(1)}</div>
                    <div className="text-xs text-slate-500">RMSE</div>
                  </div>
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{stats.statistics.bias.toFixed(1)}</div>
                    <div className="text-xs text-slate-500">Bias</div>
                  </div>
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{pct(stats.statistics.bust_rate)}</div>
                    <div className="text-xs text-slate-500">Bust Rate</div>
                  </div>
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{stats.statistics.sample_count}</div>
                    <div className="text-xs text-slate-500">Samples</div>
                  </div>
                  <div className="rounded bg-slate-50 p-3">
                    <div className="text-xl font-bold">{stats.lead_day ? `D${stats.lead_day}` : "All"}</div>
                    <div className="text-xs text-slate-500">Lead Day</div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  Choose a region above to view MAE, RMSE, bias and bust rate.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
