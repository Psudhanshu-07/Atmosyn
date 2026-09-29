import { useState } from "react";
import {
  Brain,
  CloudRain,
  History,
  Layers,
  MapPin,
  Sliders,
} from "lucide-react";

const STAGES = [
  {
    step: "01",
    title: "NWP Forecast Run",
    icon: CloudRain,
    summary: "Medium-range numerical weather prediction (Day 1–Day 10).",
    details:
      "Global Forecast System (GFS) 0.25° gridded forecast output initialized at 00 UTC. Captures predicted rainfall, temperature, wind, pressure and humidity.",
  },
  {
    step: "02",
    title: "Historical Errors & Matching",
    icon: History,
    summary: "Forecasts paired with verified observations.",
    details:
      "Prior forecasts matched with actual ground-truth observations on location, lead day and valid time. Absolute forecast errors and climatology-scaled bust labels (>20–60 mm) are computed.",
  },
  {
    step: "03",
    title: "Atmospheric & Run Features",
    icon: Layers,
    summary: "Anti-leakage feature engineering.",
    details:
      "Features calculated exclusively from data available prior to the forecast run: rolling MAE, historical bust rate, run-to-run shift, ensemble spread, and seasonal regime.",
  },
  {
    step: "04",
    title: "ML Bust Detection",
    icon: Brain,
    summary: "XGBoost Classifier + Regressor.",
    details:
      "Dual model architecture: XGBoost classifier predicts raw bust likelihood; XGBoost regressor estimates expected continuous error magnitude. Calibrated with Isotonic Regression.",
  },
  {
    step: "05",
    title: "AI Forecast Reliability",
    icon: Sliders,
    summary: "Calibrated probability & SHAP attribution.",
    details:
      "Confidence = 1 − Calibrated Bust Probability. Tree-based SHAP determines the dominant meteorological and historical drivers behind elevated uncertainty.",
  },
  {
    step: "06",
    title: "Operational Decision Layer",
    icon: MapPin,
    summary: "India Map, 10-day outlook & alerts.",
    details:
      "Translates complex NWP verification into interactive maps, regional lead-day reliability profiles, and AI reliability alerts — supporting forecasters and planners.",
  },
];

export function HowItWorksFlow() {
  const [activeStage, setActiveStage] = useState(0);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">How Does Bust Detection Work?</h2>
          <p className="text-xs text-slate-500">
            End-to-end scientific pipeline from NWP initialization to calibrated AI reliability
          </p>
        </div>
        <span className="rounded-full bg-sky-50 px-2.5 py-0.5 text-xs font-semibold text-sky-700 border border-sky-200">
          Scientific Pipeline
        </span>
      </div>

      {/* Pipeline stepper */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {STAGES.map((s, idx) => {
          const Icon = s.icon;
          const isSelected = activeStage === idx;
          return (
            <button
              key={s.step}
              type="button"
              onClick={() => setActiveStage(idx)}
              className={`flex flex-col items-start rounded-lg border p-3 text-left transition-all cursor-pointer ${
                isSelected
                  ? "border-sky-500 bg-sky-50/70 shadow-sm"
                  : "border-slate-200 bg-slate-50/50 hover:bg-slate-100/70 text-slate-700"
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <span className={`text-[10px] font-bold ${isSelected ? "text-sky-600" : "text-slate-400"}`}>
                  STAGE {s.step}
                </span>
                <Icon size={16} className={isSelected ? "text-sky-600" : "text-slate-400"} />
              </div>
              <div className="mt-2 text-xs font-bold leading-tight text-slate-800">{s.title}</div>
              <div className="mt-1 line-clamp-2 text-[11px] text-slate-500">{s.summary}</div>
            </button>
          );
        })}
      </div>

      {/* Selected stage details view */}
      <div className="mt-4 rounded-lg bg-slate-900 p-4 text-white">
        <div className="flex items-center gap-2">
          <span className="rounded bg-sky-500/20 px-2 py-0.5 text-xs font-mono font-semibold text-sky-300">
            Stage {STAGES[activeStage].step} of 06
          </span>
          <h3 className="font-semibold text-sm text-slate-100">{STAGES[activeStage].title}</h3>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          {STAGES[activeStage].details}
        </p>
      </div>
    </div>
  );
}
