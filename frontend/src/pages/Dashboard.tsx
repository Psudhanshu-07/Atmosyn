import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Clock,
  Compass,
  Database,
  MapPin,
} from "lucide-react";
import { Api } from "../lib/api";
import type {
  Alert,
  DashboardKpis,
  MapConfidenceResponse,
  MapRegionPoint,
  TenDayResponse,
} from "../lib/types";
import { DaySelector } from "../components/DaySelector";
import { VariableSelector } from "../components/VariableSelector";
import { KpiCard } from "../components/KpiCard";
import { IndiaMap, MapLegend } from "../components/IndiaMap";
import { RegionDrawer } from "../components/RegionDrawer";
import { ErrorCard, LoadingCard } from "../components/LoadingError";
import { RiskBadge } from "../components/RiskBadge";
import { InfoTooltip } from "../components/InfoTooltip";
import { HowItWorksFlow } from "../components/HowItWorks";
import { VARIABLE_LABELS, VARIABLE_UNITS, fmtTime, pct } from "../lib/format";
import { useAppStore } from "../store";

export function DashboardPage() {
  const {
    selectedLeadDay: leadDay,
    setSelectedLeadDay,
    selectedVariable: variable,
    setSelectedVariable,
    setSelectedRegion,
    userMode,
  } = useAppStore();

  const navigate = useNavigate();
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [mapData, setMapData] = useState<MapConfidenceResponse | null>(null);
  const [trend, setTrend] = useState<TenDayResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerRegion, setDrawerRegion] = useState<MapRegionPoint | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [k, m, t, a] = await Promise.all([
        Api.dashboardKpis(leadDay, variable),
        Api.mapConfidence(leadDay, variable),
        Api.confidence10day("MH_MUM", variable).catch(() => null),
        Api.alerts().catch(() => []),
      ]);
      setKpis(k);
      setMapData(m);
      setTrend(t);
      setAlerts(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [leadDay, variable]);

  useEffect(() => {
    load();
  }, [load]);

  const sortedAlerts = useMemo(
    () => [...alerts].sort((a, b) => b.bust_probability - a.bust_probability).slice(0, 5),
    [alerts],
  );

  const highRiskRegions = useMemo(
    () =>
      (mapData?.regions ?? [])
        .filter((r) => r.risk_level === "HIGH" || r.risk_level === "VERY_HIGH")
        .sort((a, b) => (b.bust_probability ?? 0) - (a.bust_probability ?? 0)),
    [mapData],
  );

  return (
    <div className="space-y-5">
      {/* Overview Header (Master Prompt §22) */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/80 pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            BUSTRA Overview
          </h1>
          <p className="text-xs text-slate-500">
            Understand where and when medium-range numerical weather forecasts (Day 1–10) may experience elevated error risk.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <VariableSelector value={variable} onChange={setSelectedVariable} />
          <DaySelector value={leadDay} onChange={setSelectedLeadDay} />
        </div>
      </div>

      {/* 30-Second Common User Quick Answer (Master Prompt §50) */}
      {userMode === "simple" && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5 rounded-xl border border-sky-100 bg-linear-to-r from-sky-50/70 to-indigo-50/50 p-3.5 text-xs shadow-xs">
          <div className="space-y-0.5">
            <span className="font-bold text-sky-900 uppercase tracking-wider text-[10px]">1. Where?</span>
            <div className="font-semibold text-slate-800">
              {highRiskRegions.length > 0
                ? `${highRiskRegions[0].region_name} & ${highRiskRegions.length} other regions`
                : "All regions currently within normal error bounds"}
            </div>
            <div className="text-[11px] text-slate-500">Highest forecast uncertainty</div>
          </div>
          <div className="space-y-0.5">
            <span className="font-bold text-sky-900 uppercase tracking-wider text-[10px]">2. When?</span>
            <div className="font-semibold text-slate-800">Lead Day {leadDay}</div>
            <div className="text-[11px] text-slate-500">
              Peak overall risk: Day {kpis?.highest_risk_lead_day ?? leadDay}
            </div>
          </div>
          <div className="space-y-0.5">
            <span className="font-bold text-sky-900 uppercase tracking-wider text-[10px]">3. How Much Risk?</span>
            <div className="font-semibold text-slate-800">
              {highRiskRegions.length > 0
                ? `${pct(highRiskRegions[0].bust_probability)} Max Bust Prob.`
                : "Low across monitored grid"}
            </div>
            <div className="text-[11px] text-slate-500">Probability of significant forecast error</div>
          </div>
          <div className="space-y-0.5">
            <span className="font-bold text-sky-900 uppercase tracking-wider text-[10px]">4. Why?</span>
            <div className="font-semibold text-slate-800">Historical instability & lead time</div>
            <div className="text-[11px] text-slate-500">Driven by past local error patterns</div>
          </div>
          <div className="space-y-0.5">
            <span className="font-bold text-sky-900 uppercase tracking-wider text-[10px]">5. Reliability Level</span>
            <div className="font-semibold text-slate-800">
              {kpis ? pct(kpis.avg_confidence) : "—"} Average
            </div>
            <div className="text-[11px] text-slate-500">Calibrated AI confidence score</div>
          </div>
        </div>
      )}

      {error && <ErrorCard title="Unable to load dashboard" message={error} onRetry={load} />}
      {loading && <LoadingCard label="Evaluating regional forecast reliability..." />}

      {!loading && !error && kpis && mapData && (
        <>
          {/* Top KPI Cards with Tooltips (Master Prompt §22 & §30) */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard
              label="Regions Monitored"
              value={kpis.regions_monitored}
              sub="Indian synoptic network"
              onClick={() => navigate("/map")}
            />
            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-xs">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <InfoTooltip term="forecast_bust" mode={userMode}>
                  <span>High-Risk Regions</span>
                </InfoTooltip>
                <AlertTriangle size={15} className={kpis.high_risk_regions > 0 ? "text-orange-500" : "text-slate-300"} />
              </div>
              <div className={`mt-1 text-2xl font-bold ${kpis.high_risk_regions > 0 ? "text-orange-600" : "text-slate-900"}`}>
                {kpis.high_risk_regions}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500">
                Day {leadDay} · {VARIABLE_LABELS[variable]}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-xs">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <InfoTooltip term="confidence" mode={userMode}>
                  <span>Avg Confidence</span>
                </InfoTooltip>
                <Compass size={15} className="text-sky-500" />
              </div>
              <div className="mt-1 text-2xl font-bold text-slate-900">
                {pct(kpis.avg_confidence)}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500">AI-derived reliability</div>
            </div>

            <div
              onClick={() => setSelectedLeadDay(kpis.highest_risk_lead_day)}
              className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-xs cursor-pointer hover:border-sky-300 transition-all"
            >
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Peak Risk Lead</span>
                <Clock size={15} className="text-amber-500" />
              </div>
              <div className="mt-1 text-2xl font-bold text-slate-900">
                Day {kpis.highest_risk_lead_day}
              </div>
              <div className="mt-0.5 text-[11px] text-sky-600 font-medium">Click to select Day {kpis.highest_risk_lead_day}</div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-xs">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Data Freshness</span>
                <Database size={15} className="text-emerald-500" />
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900">
                {fmtTime(kpis.forecast_run)}
              </div>
              <div className="mt-0.5 text-[11px] font-semibold text-emerald-600">
                ● {kpis.data_status} (00 UTC Cycle)
              </div>
            </div>
          </div>

          {/* Central India Reliability Map (Master Prompt §23) */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
              <div>
                <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <MapPin size={16} className="text-sky-600" />
                  India Forecast Reliability Map — Day {leadDay} {VARIABLE_LABELS[variable]}
                </h2>
                <p className="text-xs text-slate-500">
                  Color and circle diameter reflect model-estimated forecast bust risk. Click any region to inspect SHAP drivers and error profiles.
                </p>
              </div>
              <span className="rounded bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-700">
                {mapData.regions.length} Stations Monitored
              </span>
            </div>

            <IndiaMap
              data={mapData}
              selectedRegionId={drawerRegion?.region_id}
              onRegionClick={setDrawerRegion}
            />
            <MapLegend />
          </div>

          {/* 10-Day Outlook + Alerts Grid (Master Prompt §22 & §26) */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* 10-Day Reliability Outlook */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Calendar size={15} className="text-sky-600" />
                    Day 1–Day 10 Reliability Outlook · Mumbai Reference
                  </h3>
                  <p className="text-xs text-slate-500">
                    Lead-time error growth across the 10-day medium range
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedRegion("MH_MUM");
                    navigate("/region");
                  }}
                  className="text-xs font-semibold text-sky-600 hover:text-sky-800"
                >
                  Full Profile →
                </button>
              </div>

              {trend ? (
                <div className="space-y-1.5">
                  {trend.days.map((d) => (
                    <div
                      key={d.lead_day}
                      onClick={() => setSelectedLeadDay(d.lead_day)}
                      className={`flex items-center gap-2 p-1 rounded-md transition-all cursor-pointer ${
                        leadDay === d.lead_day ? "bg-sky-50/80 ring-1 ring-sky-300" : "hover:bg-slate-50"
                      }`}
                    >
                      <span className="w-9 text-xs font-bold text-slate-700">Day {d.lead_day}</span>
                      <div className="h-5 flex-1 overflow-hidden rounded bg-slate-100 relative">
                        <div
                          className={`h-full rounded transition-all ${
                            d.confidence > 0.6
                              ? "bg-emerald-500"
                              : d.confidence > 0.4
                              ? "bg-amber-500"
                              : "bg-orange-500"
                          }`}
                          style={{ width: `${d.confidence * 100}%` }}
                        />
                      </div>
                      <span className="w-12 text-right text-xs font-semibold text-slate-800">
                        {pct(d.confidence)}
                      </span>
                      <span className="w-16 text-right text-[11px] text-slate-500 hidden sm:inline">
                        ±{d.expected_error} {VARIABLE_UNITS[variable]}
                      </span>
                      <RiskBadge level={d.risk_level} showProbability={false} size="sm" />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">10-day trend data loading...</p>
              )}
            </div>

            {/* AI Reliability Alerts (Master Prompt §29) */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <AlertTriangle size={15} className="text-amber-500" />
                    Active AI Reliability Alerts
                  </h3>
                  <p className="text-xs text-slate-500">
                    Flagging high bust risk — <b>not</b> official severe weather warnings
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/alerts")}
                  className="text-xs font-semibold text-sky-600 hover:text-sky-800"
                >
                  View all ({alerts.length}) →
                </button>
              </div>

              {sortedAlerts.length === 0 ? (
                <div className="rounded-lg bg-emerald-50/50 p-4 text-center text-xs text-emerald-800 border border-emerald-100">
                  <CheckCircle size={20} className="mx-auto mb-1 text-emerald-600" />
                  No regions currently exceed the active alert threshold for Day {leadDay}.
                </div>
              ) : (
                <ul className="divide-y divide-slate-100 text-xs">
                  {sortedAlerts.map((a) => (
                    <li
                      key={a.alert_id}
                      onClick={() => {
                        setSelectedRegion(a.region_id);
                        navigate("/detection");
                      }}
                      className="flex items-center justify-between py-2 hover:bg-slate-50 px-1 rounded cursor-pointer transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-slate-900">{a.region_name}</div>
                        <div className="text-[11px] text-slate-500">
                          {a.variable.replace("_", " ")} · Lead Day {a.lead_day}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-orange-600">{pct(a.bust_probability)} Bust Risk</span>
                        <RiskBadge level={a.risk_level} showProbability={false} size="sm" />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* How Does This Work Component (Master Prompt §33) */}
          <HowItWorksFlow />
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
