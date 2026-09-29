import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Api } from "../lib/api";
import type { Variable, VerificationPair } from "../lib/types";
import { ErrorCard, LoadingCard } from "./LoadingError";
import { VARIABLE_LABELS } from "../lib/format";

export function ForecastVerificationChart({
  regionId,
  variable,
  leadDay,
}: {
  regionId: string;
  variable: Variable;
  leadDay?: number;
}) {
  const [pairs, setPairs] = useState<VerificationPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Api.forecastVerification(regionId, variable, leadDay, 25)
      .then((res) => setPairs(res.pairs))
      .catch((e) => setError(e instanceof Error ? e.message : "Verification data unavailable"))
      .finally(() => setLoading(false));
  }, [regionId, variable, leadDay]);

  if (loading) return <LoadingCard label="Loading forecast verification history..." />;
  if (error) return <ErrorCard title="Verification history unavailable" message={error} />;
  if (pairs.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500 text-center">
        Insufficient historical cases for verification comparison.
      </div>
    );
  }

  const chartData = pairs.map((p) => ({
    date: p.valid_time ? p.valid_time.slice(5, 10) : "—",
    forecast: p.forecast_value,
    observed: p.observed_value,
    error: p.absolute_error,
    bust: p.bust,
    threshold: p.bust_threshold,
  }));

  const unit = pairs[0]?.unit ?? "";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <div>
          <h3 className="text-sm font-bold text-slate-900">
            Historical Forecast vs Observed Verification
          </h3>
          <p className="text-xs text-slate-500">
            This chart shows how past numerical forecasts compared with what was later observed. Differences reflect normal NWP uncertainty unless exceeding the bust threshold.
          </p>
        </div>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
          {VARIABLE_LABELS[variable]} ({unit})
        </span>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} unit={` ${unit}`} />
            <ReTooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="rounded-md border border-slate-200 bg-white p-2.5 text-xs shadow-lg">
                    <div className="font-bold text-slate-800">Valid: {d.date}</div>
                    <div className="mt-1 text-sky-600">
                      Forecast: <b>{d.forecast} {unit}</b>
                    </div>
                    <div className="text-emerald-600">
                      Observed: <b>{d.observed} {unit}</b>
                    </div>
                    <div className="text-slate-700">
                      Forecast Error: <b>{d.error} {unit}</b>
                    </div>
                    <div className="mt-1 pt-1 border-t border-slate-100 text-[10px]">
                      Threshold: {d.threshold} {unit} · {d.bust ? "⚠️ Forecast Bust" : "✓ Within Normal Bounds"}
                    </div>
                  </div>
                );
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast Value"
              stroke="#0284c7"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="observed"
              name="Observed Ground Truth"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="error"
              name="Forecast Error"
              stroke="#f97316"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
        <span>Displaying latest {pairs.length} chronological verification cycles</span>
        <span className="font-medium text-slate-700">
          Bust threshold for {variable}: {pairs[0]?.bust_threshold} {unit}
        </span>
      </div>
    </div>
  );
}
