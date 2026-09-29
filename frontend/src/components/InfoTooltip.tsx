import { useState } from "react";
import { HelpCircle } from "lucide-react";

export const GLOSSARY: Record<string, { title: string; explanation: string; simple: string }> = {
  bust_probability: {
    title: "Bust Probability",
    explanation:
      "The calibrated AI estimate of the likelihood that the NWP forecast error will exceed the documented significant-error threshold (e.g. >20–60 mm for rainfall).",
    simple:
      "Chance that this forecast will be significantly wrong. High probability = forecast is likely unreliable.",
  },
  confidence: {
    title: "AI Forecast Reliability (Confidence)",
    explanation:
      "Derived reliability metric (1 − Calibrated Bust Probability). It is an AI reliability layer and NOT an official meteorological confidence score.",
    simple:
      "How dependable this forecast is expected to be. Higher = more reliable forecast.",
  },
  forecast_error: {
    title: "Forecast Error",
    explanation:
      "The difference between numerical model prediction and subsequently verified ground observation (|forecast − observed|).",
    simple:
      "Difference between what was predicted and what actually happened.",
  },
  forecast_bust: {
    title: "Forecast Bust",
    explanation:
      "A situation where NWP forecast error exceeds the threshold of operational tolerance (rainfall: climatology-scaled 20–60 mm, temperature: 5°C, wind: 10 m/s).",
    simple:
      "A forecast that failed significantly beyond normal acceptable error.",
  },
  mae: {
    title: "Mean Absolute Error (MAE)",
    explanation:
      "Average magnitude of errors between past forecasts and matching observations over the historical archive without considering direction.",
    simple:
      "Average error size for this region and lead time over historical cases.",
  },
  rmse: {
    title: "Root Mean Square Error (RMSE)",
    explanation:
      "Square root of the mean squared errors; gives higher weight to large forecast errors.",
    simple:
      "Statistical measure emphasizing large, severe forecast errors.",
  },
  bias: {
    title: "Forecast Bias (Signed Error)",
    explanation:
      "Average signed difference (forecast − observed). Positive indicates systematic over-prediction (wet/warm bias); negative indicates under-prediction.",
    simple:
      "Whether the model tends to predict too much (positive) or too little (negative).",
  },
  ensemble_spread: {
    title: "Ensemble Spread",
    explanation:
      "Standard deviation or disagreement across GEFS/ensemble members. Higher spread signifies higher atmospheric flow uncertainty.",
    simple:
      "How much different computer model scenarios disagree with each other.",
  },
  run_change: {
    title: "Run-to-Run Change",
    explanation:
      "Relative shift between the current NWP model run and the previous run (e.g. 00 UTC vs 12 UTC) for the exact same target valid time.",
    simple:
      "How much the forecast shifted compared to the previous computer run.",
  },
};

export function InfoTooltip({
  term,
  mode = "simple",
  children,
}: {
  term: keyof typeof GLOSSARY;
  mode?: "simple" | "technical";
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const info = GLOSSARY[term];
  if (!info) return <>{children}</>;

  return (
    <span className="relative inline-flex items-center gap-1 group">
      {children}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="text-slate-400 hover:text-sky-600 focus:outline-none p-0.5 rounded cursor-pointer"
        aria-label={`Explanation for ${info.title}`}
      >
        <HelpCircle size={13} />
      </button>

      {open && (
        <div
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-1.5 w-64 -translate-x-1/2 rounded-md bg-slate-900 p-2.5 text-xs text-white shadow-xl ring-1 ring-slate-800"
        >
          <div className="font-semibold text-sky-300">{info.title}</div>
          <p className="mt-1 leading-snug text-slate-200">
            {mode === "technical" ? info.explanation : info.simple}
          </p>
          <div className="absolute top-full left-1/2 -ml-1 border-4 border-transparent border-t-slate-900" />
        </div>
      )}
    </span>
  );
}
