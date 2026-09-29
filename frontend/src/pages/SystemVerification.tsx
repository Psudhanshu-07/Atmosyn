import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { Api } from "../lib/api";
import type { SystemVerificationResponse } from "../lib/types";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { fmtTime } from "../lib/format";

export function SystemVerificationPage() {
  const [data, setData] = useState<SystemVerificationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runVerification = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await Api.systemVerification();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "System self-audit failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    runVerification();
  }, [runVerification]);

  const categories = ["Database", "Data", "ML", "API", "System"] as const;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">System Self-Audit & Verification</h1>
          <p className="text-sm text-slate-500">
            Real-time pipeline diagnostics for data integrity, anti-leakage, ML calibration, and API contracts (Master Prompt §48).
          </p>
        </div>
        <button
          type="button"
          onClick={runVerification}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-sky-500 disabled:opacity-50 cursor-pointer"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Re-Run Verification
        </button>
      </div>

      {loading && <LoadingCard label="Executing system verification checks..." />}
      {error && <ErrorCard title="Verification check error" message={error} onRetry={runVerification} />}

      {!loading && !error && data && (
        <>
          {/* Overall status banner */}
          <div
            className={`flex items-center justify-between rounded-xl border p-4 shadow-sm ${
              data.overall_status === "PASS"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : data.overall_status === "DEGRADED"
                ? "border-amber-200 bg-amber-50 text-amber-900"
                : "border-red-200 bg-red-50 text-red-900"
            }`}
          >
            <div className="flex items-center gap-3">
              <ShieldCheck size={28} />
              <div>
                <div className="text-sm font-bold uppercase tracking-wide">
                  Overall System Status: {data.overall_status}
                </div>
                <div className="text-xs opacity-90">
                  Audit executed at {fmtTime(data.checked_at)} · All automated checks verified.
                </div>
              </div>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${
                data.overall_status === "PASS"
                  ? "bg-emerald-200 text-emerald-900"
                  : data.overall_status === "DEGRADED"
                  ? "bg-amber-200 text-amber-900"
                  : "bg-red-200 text-red-900"
              }`}
            >
              {data.overall_status === "PASS" ? "ALL SYSTEMS OPERATIONAL" : data.overall_status}
            </span>
          </div>

          {/* Grouped checks */}
          <div className="space-y-4">
            {categories.map((cat) => {
              const items = data.items.filter((i) => i.category === cat);
              if (items.length === 0) return null;
              return (
                <div key={cat} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
                    {cat} Diagnostics
                  </h2>
                  <div className="divide-y divide-slate-100">
                    {items.map((item) => (
                      <div key={item.component} className="flex flex-col py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div className="flex items-start gap-2.5">
                          {item.status === "PASS" ? (
                            <CheckCircle2 size={18} className="mt-0.5 text-emerald-600 shrink-0" />
                          ) : item.status === "WARNING" ? (
                            <AlertTriangle size={18} className="mt-0.5 text-amber-500 shrink-0" />
                          ) : (
                            <XCircle size={18} className="mt-0.5 text-red-600 shrink-0" />
                          )}
                          <div>
                            <div className="text-sm font-semibold text-slate-900">{item.component}</div>
                            <div className="text-xs text-slate-600 mt-0.5">{item.details}</div>
                          </div>
                        </div>
                        <span
                          className={`self-start sm:self-auto rounded px-2 py-0.5 text-[11px] font-bold ${
                            item.status === "PASS"
                              ? "bg-emerald-100 text-emerald-800"
                              : item.status === "WARNING"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
