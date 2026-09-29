import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Bell,
  Brain,
  Cloud,
  Database,
  Info,
  LayoutGrid,
  Map as MapIcon,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { Api } from "../../lib/api";
import type { Health } from "../../lib/types";
import { useAppStore } from "../../store";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, end: true },
  { to: "/india-map", label: "India Weather Map", icon: Cloud },
  { to: "/map", label: "Forecast Map", icon: MapIcon },
  { to: "/detection", label: "AI Bust Detection", icon: Brain },
  { to: "/region", label: "Region Details", icon: MapIcon },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/sources", label: "Data Sources", icon: Database },
  { to: "/verification", label: "System Verification", icon: ShieldCheck },
  { to: "/system", label: "System Health", icon: Activity },
  { to: "/methodology", label: "Methodology", icon: Info },
];

export function Layout() {
  const [health, setHealth] = useState<Health | null>(null);
  const { userMode, setUserMode } = useAppStore();

  useEffect(() => {
    Api.health().then(setHealth).catch(() => setHealth(null));
    const t = setInterval(
      () => Api.health().then(setHealth).catch(() => setHealth(null)),
      60000,
    );
    return () => clearInterval(t);
  }, []);

  const healthy = health?.status === "healthy";

  return (
    <div className="flex h-full min-h-screen flex-col bg-slate-50 text-slate-900">
      {/* Prominent Synthetic Demonstration Data Notice (Master Prompt §6, §19, §51) */}
      <div className="bg-amber-500/10 border-b border-amber-500/25 px-4 py-1.5 text-xs text-amber-900 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-950 uppercase tracking-wide">
            Prototype Notice
          </span>
          <span>
            <b>Synthetic demonstration data</b> — not an operational weather forecast. Demonstrates medium-range forecast reliability analysis.
          </span>
        </div>
        <NavLink to="/sources" className="text-[11px] font-semibold text-amber-950 underline hover:text-amber-800 hidden sm:inline">
          View Data Provenance →
        </NavLink>
      </div>

      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white shadow-xs">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-600 text-white shadow-xs">
              <Cloud size={18} />
            </div>
            <div>
              <div className="text-sm font-bold leading-tight text-slate-900 flex items-center gap-1.5">
                ATOMSYN
                <span className="rounded bg-sky-100 px-1.5 py-0.2 text-[10px] font-bold text-sky-800 uppercase">
                  Forecast Reliability
                </span>
              </div>
              <div className="text-[11px] leading-tight text-slate-500">
                AI-powered analysis of medium-range weather forecast reliability (Day 1–10)
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Common User Mode vs Technical Details Mode Toggle (Master Prompt §24) */}
            <div className="flex items-center rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setUserMode("simple")}
                className={`flex items-center gap-1 rounded-md px-2 py-1 font-medium transition-all cursor-pointer ${
                  userMode === "simple"
                    ? "bg-white text-sky-700 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                title="Simple view with plain-English summaries and practical interpretation"
              >
                <Sparkles size={12} />
                Simple
              </button>
              <button
                type="button"
                onClick={() => setUserMode("technical")}
                className={`flex items-center gap-1 rounded-md px-2 py-1 font-medium transition-all cursor-pointer ${
                  userMode === "technical"
                    ? "bg-white text-sky-700 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                title="Technical mode with SHAP values, Brier scores, error distributions and raw diagnostics"
              >
                <SlidersHorizontal size={12} />
                Technical
              </button>
            </div>

            <div className="hidden items-center gap-3 text-xs md:flex">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span
                  className={`h-2 w-2 rounded-full ${healthy ? "bg-emerald-500" : "bg-red-500"}`}
                  aria-hidden
                />
                API {healthy ? "Healthy" : "Unavailable"}
              </span>
              <span className="hidden items-center gap-1.5 text-slate-600 lg:flex">
                <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
                Model {health?.active_model ?? "xgb_v1.3"}
              </span>
            </div>
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        <nav
          aria-label="Main navigation"
          className="sticky top-[89px] hidden h-fit w-56 shrink-0 border-r border-slate-200 bg-white py-3 md:block"
        >
          <div className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }: { isActive: boolean }) =>
                  `flex items-center gap-2.5 px-4 py-2 text-xs font-semibold tracking-wide ${
                    isActive
                      ? "border-r-2 border-sky-600 bg-sky-50/80 text-sky-700"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </div>

          <div className="mt-6 border-t border-slate-100 px-4 pt-3 text-[11px] text-slate-500 space-y-1">
            <div className="font-semibold text-slate-700 uppercase tracking-wider text-[10px]">
              Target Domain
            </div>
            <div>Medium-Range NWP (Day 1–10)</div>
            <div className="text-[10px] text-slate-400">All predictions calibrated & grounded</div>
          </div>
        </nav>

        <main className="min-w-0 flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-slate-200 bg-white px-4 py-2.5">
        <div className="mx-auto max-w-7xl flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-500">
          <p className="text-center sm:text-left">
            ATOMSYN Notice: The bust probability and confidence indicators are AI-derived estimates of forecast reliability based on available forecast, historical and meteorological data. ATOMSYN does not constitute an official weather warning and does not replace forecasts, advisories or warnings issued by authorized meteorological agencies.
          </p>
          <div className="shrink-0 text-slate-400">© 2026 ATOMSYN · Forecast Reliability</div>
        </div>
      </footer>
    </div>
  );
}
