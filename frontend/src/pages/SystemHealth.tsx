import { useCallback, useEffect, useState } from "react";
import { Api } from "../lib/api";
import type { DataQuality, Health, ModelInfo } from "../lib/types";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { fmtTime } from "../lib/format";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
      aria-label={ok ? "healthy" : "unhealthy"}
    />
  );
}

export function SystemHealthPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, q, m] = await Promise.all([
        Api.health(),
        Api.dataQuality(),
        Api.models(),
      ]);
      setHealth(h);
      setQuality(q);
      setModels(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "System status unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const active = models.find((m) => m.status === "ACTIVE");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">System Health</h1>
          <p className="text-sm text-slate-500">Data, model and pipeline status</p>
        </div>
        <button
          onClick={load}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {error && <ErrorCard title="System status unavailable" message={error} onRetry={load} />}
      {loading && <LoadingCard label="Checking system health..." />}

      {!loading && !error && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              API & Services
            </h2>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-slate-600">API</span>
                <span className="flex items-center gap-2">
                  <StatusDot ok={health?.status === "healthy"} />
                  {health?.status ?? "—"}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-slate-600">Database</span>
                <span className="flex items-center gap-2">
                  <StatusDot ok={health?.database === "connected"} />
                  {health?.database ?? "—"}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-slate-600">ML Service</span>
                <span className="flex items-center gap-2">
                  <StatusDot ok={health?.ml_service !== "unavailable"} />
                  {health?.ml_service ?? "—"}
                </span>
              </li>
              <li className="flex items-center justify-between text-xs text-slate-400">
                <span>Version</span>
                <span>{health?.version}</span>
              </li>
              <li className="flex items-center justify-between text-xs text-slate-400">
                <span>Checked</span>
                <span>{fmtTime(health?.timestamp)}</span>
              </li>
            </ul>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Data Sources
            </h2>
            <div className={`mb-3 rounded-md px-3 py-1.5 text-sm font-semibold ${
              quality?.overall_status === "GOOD"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-amber-50 text-amber-700"
            }`}>
              Overall: {quality?.overall_status}
            </div>
            <ul className="space-y-2 text-sm">
              {quality?.sources.map((s) => (
                <li key={s.source} className="flex items-center justify-between">
                  <span className="text-slate-600">{s.source.replace("_", " ")}</span>
                  <span className="flex items-center gap-2">
                    <StatusDot ok={s.status === "GOOD"} />
                    <span className="text-xs text-slate-500">
                      {s.records != null ? `${s.records.toLocaleString()} rec` : s.status}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {quality?.warnings.length ? (
              <div className="mt-3 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
                {quality.warnings.map((w) => (
                  <div key={w}>⚠ {w}</div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              ML Model
            </h2>
            {active ? (
              <>
                <div className="mb-2 text-sm font-semibold text-slate-800">
                  <span className="font-mono">{active.model_version}</span>
                  <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
                    {active.status}
                  </span>
                </div>
                <div className="text-xs text-slate-500">{active.algorithm}</div>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">ROC-AUC</dt>
                    <dd className="font-bold">{active.roc_auc?.toFixed(3) ?? "—"}</dd>
                  </div>
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">Brier Score</dt>
                    <dd className="font-bold">{active.brier_score?.toFixed(4) ?? "—"}</dd>
                  </div>
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">Precision</dt>
                    <dd className="font-bold">{active.precision_?.toFixed(3) ?? "—"}</dd>
                  </div>
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">Recall</dt>
                    <dd className="font-bold">{active.recall_?.toFixed(3) ?? "—"}</dd>
                  </div>
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">F1</dt>
                    <dd className="font-bold">{active.f1?.toFixed(3) ?? "—"}</dd>
                  </div>
                  <div className="rounded bg-slate-50 p-2">
                    <dt className="text-[11px] text-slate-500">Checksum</dt>
                    <dd className="font-mono text-xs font-bold">{active.checksum}</dd>
                  </div>
                </dl>
                {active.trained_from && (
                  <div className="mt-2 text-[11px] text-slate-400">
                    Training period: {active.trained_from} → {active.trained_to}
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-slate-500">No models registered.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
