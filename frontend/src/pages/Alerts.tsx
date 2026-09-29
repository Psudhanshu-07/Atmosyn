import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Api } from "../lib/api";
import type { Alert } from "../lib/types";
import { RiskBadge } from "../components/RiskBadge";
import { EmptyCard, ErrorCard, LoadingCard } from "../components/LoadingError";
import { fmtTime, pct } from "../lib/format";
import { useAppStore } from "../store";

export function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [ackPending, setAckPending] = useState(false);
  const { setSelectedRegion } = useAppStore();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAlerts(await Api.alerts());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Alerts unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const acknowledge = async (alertId: string) => {
    setAckPending(true);
    try {
      await Api.acknowledgeAlert(alertId);
      setSelected(null);
      await load();
    } finally {
      setAckPending(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">AI Reliability Alerts</h1>
        <p className="text-sm text-slate-500">
          Regions where the AI model estimates a high probability of significant
          forecast error. These are <b>not</b> official weather warnings.
        </p>
      </div>

      {error && <ErrorCard title="Unable to load alerts" message={error} onRetry={load} />}
      {loading && <LoadingCard label="Loading alerts..." />}

      {!loading && !error && alerts.length === 0 && (
        <EmptyCard
          title="No active AI reliability alerts"
          message="No regions currently meet the configured alert threshold."
        />
      )}

      {!loading && !error && alerts.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5">Risk</th>
                <th className="px-4 py-2.5">Region</th>
                <th className="px-4 py-2.5">Variable</th>
                <th className="px-4 py-2.5">Lead Day</th>
                <th className="px-4 py-2.5">Bust Prob.</th>
                <th className="px-4 py-2.5">Confidence</th>
                <th className="px-4 py-2.5">Generated</th>
                <th className="px-4 py-2.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr
                  key={a.alert_id}
                  className="cursor-pointer border-b border-slate-100 hover:bg-sky-50"
                  onClick={() => setSelected(a)}
                >
                  <td className="px-4 py-2.5">
                    <RiskBadge level={a.risk_level} showProbability={false} size="sm" />
                  </td>
                  <td className="px-4 py-2.5 font-medium">{a.region_name}</td>
                  <td className="px-4 py-2.5 capitalize">{a.variable.replace("_", " ")}</td>
                  <td className="px-4 py-2.5">D{a.lead_day}</td>
                  <td className="px-4 py-2.5 font-semibold">{pct(a.bust_probability)}</td>
                  <td className="px-4 py-2.5">{pct(a.confidence)}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">{fmtTime(a.generated_at)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                      a.status === "ACTIVE" ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-600"
                    }`}>
                      {a.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/30 p-4"
          onClick={() => setSelected(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-widest text-orange-600">
                  AI Forecast Bust Alert
                </div>
                <h2 className="mt-0.5 text-lg font-bold text-slate-900">
                  {selected.region_name}
                </h2>
                <div className="text-sm text-slate-500">
                  {selected.variable} · Day {selected.lead_day}
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xl font-bold">{pct(selected.bust_probability)}</div>
                <div className="text-[11px] text-slate-500">Bust Probability</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xl font-bold">{pct(selected.confidence)}</div>
                <div className="text-[11px] text-slate-500">Confidence</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 flex items-center justify-center">
                <RiskBadge level={selected.risk_level} showProbability={false} />
              </div>
            </div>

            {selected.message && (
              <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
                {selected.message}
              </p>
            )}

            <div className="mt-3 space-y-1 text-xs text-slate-500">
              <div>Alert {selected.alert_id} · Model {selected.model_version}</div>
              <div>Generated {fmtTime(selected.generated_at)} · Expires {fmtTime(selected.expires_at)}</div>
            </div>

            <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              This is an AI-derived forecast reliability indicator and is not an
              official weather warning.
            </p>

            <div className="mt-4 flex gap-2">
              {selected.status === "ACTIVE" && (
                <button
                  disabled={ackPending}
                  onClick={() => acknowledge(selected.alert_id)}
                  className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                >
                  {ackPending ? "Acknowledging..." : "Acknowledge"}
                </button>
              )}
              <button
                onClick={() => {
                  setSelectedRegion(selected.region_id);
                  navigate("/detection");
                }}
                className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
              >
                Open in AI Detection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
