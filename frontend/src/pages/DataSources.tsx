import { useEffect, useState } from "react";
import { ExternalLink, BookOpen, RefreshCw } from "lucide-react";
import { Api } from "../lib/api";
import type { DataSource, GFSStatusResponse } from "../lib/types";
import { ErrorCard, LoadingCard } from "../components/LoadingError";

export function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [gfsStatus, setGfsStatus] = useState<GFSStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatingGfs, setUpdatingGfs] = useState(false);
  const [gfsMsg, setGfsMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    Promise.all([
      Api.dataSources().then(setSources),
      Api.gfsStatus().then(setGfsStatus).catch(() => null),
    ])
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load sources"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleGfsUpdate = async () => {
    setUpdatingGfs(true);
    setGfsMsg(null);
    try {
      const res = await Api.gfsUpdate(false);
      setGfsMsg(res.message);
      const updated = await Api.gfsStatus();
      setGfsStatus(updated);
    } catch (e) {
      setGfsMsg(e instanceof Error ? e.message : "NOMADS check failed");
    } finally {
      setUpdatingGfs(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Data Sources & Provenance</h1>
        <p className="text-sm text-slate-500">
          Authoritative meteorological datasets, resolutions, licenses, and grounding specifications (PRD §4, §5, §31).
        </p>
      </div>

      <div className="rounded-lg border border-sky-200 bg-sky-50/60 p-4 text-xs text-sky-900">
        <div className="font-semibold text-sky-950 flex items-center gap-1.5 mb-1">
          <BookOpen size={15} />
          Data Provenance Standard
        </div>
        Every displayed forecast reliability estimate is derived strictly by comparing NWP model runs against corresponding observations at identical locations, lead times, and units. Data sources are explicitly categorized as <b>Operational Forecast</b>, <b>Ground Truth Surface Observation</b>, <b>Atmospheric Reanalysis</b>, or <b>Satellite Observation</b>.
      </div>

      {/* Live NOAA NOMADS Ingestion Service Banner */}
      {gfsStatus && (
        <div className="rounded-xl border border-indigo-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <h2 className="text-sm font-bold text-slate-900">
                NOAA/NCEP NOMADS Live Forecast Ingestion Service
              </h2>
              <span className="rounded bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                PUBLIC DOMAIN · NO API KEY
              </span>
            </div>
            <button
              type="button"
              onClick={handleGfsUpdate}
              disabled={updatingGfs}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw size={13} className={updatingGfs ? "animate-spin" : ""} />
              {updatingGfs ? "Querying NOMADS..." : "Check NOMADS For Newer Cycle"}
            </button>
          </div>

          {gfsMsg && (
            <div className="mt-3 rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-700">
              <b>Result:</b> {gfsMsg}
            </div>
          )}

          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="rounded-lg bg-slate-50 p-2.5">
              <div className="text-[11px] font-semibold text-slate-500 uppercase">Active GFS Cycle</div>
              <div className="mt-1 font-mono text-sm font-bold text-slate-900">
                {gfsStatus.active_run ? `${gfsStatus.active_run.run_date} ${gfsStatus.active_run.cycle} UTC` : "None"}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-2.5">
              <div className="text-[11px] font-semibold text-slate-500 uppercase">GRIB2 Files Validated</div>
              <div className="mt-1 font-mono text-sm font-bold text-emerald-700">
                {gfsStatus.active_run ? `${gfsStatus.active_run.files_valid} / ${gfsStatus.active_run.files_total} files` : "0"}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-2.5">
              <div className="text-[11px] font-semibold text-slate-500 uppercase">Subregion Bounding Box</div>
              <div className="mt-1 text-xs font-medium text-slate-800">
                68°–98°E, 6°–38°N (India)
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-2.5">
              <div className="text-[11px] font-semibold text-slate-500 uppercase">Auto-Sync Cycle</div>
              <div className="mt-1 text-xs font-medium text-slate-800">
                Every {gfsStatus.update_interval_minutes}m (Background)
              </div>
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2.5">
            <span>
              Public Endpoint: <code className="text-slate-700">{gfsStatus.source_url}cgi-bin/filter_gfs_0p25.pl</code>
            </span>
            <span>
              Model Output Type: <span className="font-semibold text-slate-700">{gfsStatus.data_type}</span> (Not an observation)
            </span>
          </div>
        </div>
      )}

      {loading && <LoadingCard label="Loading data sources..." />}
      {error && <ErrorCard title="Data sources unavailable" message={error} />}

      {!loading && !error && (
        <div className="grid gap-4 lg:grid-cols-2">
          {sources.map((src) => (
            <div
              key={src.id}
              className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-300 transition-all"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-600 uppercase">
                      {src.id}
                    </span>
                    <h2 className="mt-1 text-base font-bold text-slate-900">{src.name}</h2>
                    <p className="text-xs font-medium text-slate-500">{src.provider}</p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      src.status === "OPERATIONAL_READY"
                        ? "bg-emerald-100 text-emerald-800"
                        : src.status === "REFERENCE"
                        ? "bg-indigo-100 text-indigo-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {src.status.replace("_", " ")}
                  </span>
                </div>

                <p className="mt-3 text-xs leading-relaxed text-slate-700">{src.purpose}</p>

                <div className="mt-4 space-y-2 border-t border-slate-100 pt-3 text-xs">
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Dataset:</span>
                    <span className="col-span-2 text-slate-800">{src.dataset}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Spatial Grid:</span>
                    <span className="col-span-2 text-slate-800">{src.spatial_resolution}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Temporal:</span>
                    <span className="col-span-2 text-slate-800">{src.temporal_resolution}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Update Cycle:</span>
                    <span className="col-span-2 text-slate-800">{src.update_frequency}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Archive Span:</span>
                    <span className="col-span-2 text-slate-800">{src.historical_coverage}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Variables:</span>
                    <span className="col-span-2 text-slate-800 flex flex-wrap gap-1">
                      {src.variables.map((v) => (
                        <span key={v} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                          {v}
                        </span>
                      ))}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">License:</span>
                    <span className="col-span-2 text-slate-800">{src.license_terms}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-slate-500">Access:</span>
                    <span className="col-span-2 text-slate-800">{src.access_requirements}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <span className="font-semibold text-amber-700">Limitations:</span>
                    <span className="col-span-2 text-amber-900 bg-amber-50/50 p-1.5 rounded">{src.limitations}</span>
                  </div>
                </div>
              </div>

              <div className="mt-4 border-t border-slate-100 pt-3">
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-600 hover:text-sky-800"
                >
                  Official Dataset Portal <ExternalLink size={13} />
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
