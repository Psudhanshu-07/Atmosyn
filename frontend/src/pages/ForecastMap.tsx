import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Api } from "../lib/api";
import type { MapConfidenceResponse, MapRegionPoint } from "../lib/types";
import { DaySelector } from "../components/DaySelector";
import { VariableSelector } from "../components/VariableSelector";
import { IndiaMap, MapLegend } from "../components/IndiaMap";
import { RegionDrawer } from "../components/RegionDrawer";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { useAppStore } from "../store";
import { fmtTime } from "../lib/format";

export function ForecastMapPage() {
  const {
    selectedLeadDay: leadDay,
    setSelectedLeadDay,
    selectedVariable: variable,
    setSelectedVariable,
    setSelectedRegion,
  } = useAppStore();

  const [data, setData] = useState<MapConfidenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerRegion, setDrawerRegion] = useState<MapRegionPoint | null>(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await Api.mapConfidence(leadDay, variable));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load map");
    } finally {
      setLoading(false);
    }
  }, [leadDay, variable]);

  useEffect(() => {
    load();
  }, [load]);

  const highRisk = (data?.regions ?? []).filter(
    (r) => r.risk_level === "HIGH" || r.risk_level === "VERY_HIGH",
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Forecast Map</h1>
          <p className="text-sm text-slate-500">
            Run {fmtTime(data?.forecast_run)} · {data?.data_status}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <VariableSelector value={variable} onChange={setSelectedVariable} />
          <DaySelector value={leadDay} onChange={setSelectedLeadDay} />
        </div>
      </div>

      {error && <ErrorCard title="Unable to load confidence map" message={error} onRetry={load} />}
      {loading && <LoadingCard label="Loading confidence map..." />}

      {!loading && !error && data && (
        <>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <IndiaMap
              data={data}
              selectedRegionId={drawerRegion?.region_id}
              onRegionClick={setDrawerRegion}
            />
            <MapLegend />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Error-Prone Areas — Day {leadDay} {variable}
            </h2>
            {highRisk.length === 0 ? (
              <p className="text-sm text-slate-500">
                No regions exceed the moderate-risk threshold for this day.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-4">Region</th>
                      <th className="py-2 pr-4">Lead Time</th>
                      <th className="py-2 pr-4">Bust Probability</th>
                      <th className="py-2 pr-4">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {highRisk.map((r) => (
                      <tr
                        key={r.region_id}
                        className="cursor-pointer border-b border-slate-100 hover:bg-sky-50"
                        onClick={() => setDrawerRegion(r)}
                      >
                        <td className="py-2 pr-4 font-medium">
                          {r.region_name}
                          <span className="ml-2 text-xs text-slate-400">{r.state}</span>
                        </td>
                        <td className="py-2 pr-4">Day {leadDay}</td>
                        <td className="py-2 pr-4 font-semibold">
                          {((r.bust_probability ?? 0) * 100).toFixed(0)}%
                        </td>
                        <td className="py-2 pr-4">{r.risk_level}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {drawerRegion && (
        <RegionDrawer
          region={drawerRegion}
          variable={variable}
          leadDay={leadDay}
          onClose={() => setDrawerRegion(null)}
          onOpenDetails={(id) => {
            setSelectedRegion(id);
            setDrawerRegion(null);
            navigate("/detection");
          }}
        />
      )}
    </div>
  );
}
