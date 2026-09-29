import { DISCLAIMER } from "../lib/constants";

const STEPS = [
  {
    title: "1. NWP Forecast",
    body: "Medium-range numerical weather prediction values (rainfall, temperature, wind) for Day 1–Day 10 at each monitored region.",
  },
  {
    title: "2. Historical Forecast Errors",
    body: "Every past forecast is paired with the corresponding observation (matched on region, valid time and lead day) and its error is computed: error = |forecast − observed|.",
  },
  {
    title: "3. Bust Labelling",
    body: "A forecast is labelled a bust when its error exceeds a documented, climatology-scaled threshold (rainfall: 20–60 mm depending on the region's normal rainfall). Labels are deterministic and reproducible.",
  },
  {
    title: "4. Feature Engineering",
    body: "Per forecast: lead day, forecast magnitude, historical MAE/RMSE/bust-rate (computed only from data available before the forecast), run-to-run change, ensemble spread, atmospheric context and season.",
  },
  {
    title: "5. ML Bust Detection",
    body: "An XGBoost classifier estimates the probability of a bust; an XGBoost regressor estimates the expected error magnitude. A logistic-regression baseline is trained for comparison.",
  },
  {
    title: "6. Probability Calibration",
    body: "Raw model probabilities are recalibrated with isotonic regression on a held-out validation period, so a predicted 70% behaves like ~70% frequency over many cases (evaluated with the Brier score).",
  },
  {
    title: "7. Explainable AI",
    body: "SHAP values identify which features pushed each prediction up or down. The human-readable explanation is generated only from these structured outputs — never invented.",
  },
  {
    title: "8. Confidence & Risk",
    body: "Confidence = 1 − bust probability. Probabilities map to five risk bands: 0–20% Very Low, 20–40% Low, 40–60% Moderate, 60–80% High, 80–100% Very High.",
  },
];

export function MethodologyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Methodology</h1>
        <p className="text-sm text-slate-500">
          How the forecast-reliability layer works — and what it is not.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          How It Works
        </h2>
        <ol className="space-y-4">
          {STEPS.map((s) => (
            <li key={s.title} className="border-l-4 border-sky-500 pl-4">
              <div className="font-semibold text-slate-800">{s.title}</div>
              <p className="text-sm text-slate-600">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          What This System Is Not
        </h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
          <li>It does not replace the NWP forecast or any official forecast.</li>
          <li>It does not issue weather warnings of any kind.</li>
          <li>
            It answers: <i>where, when and why</i> is the forecast likely to be
            unreliable — never <i>what weather will happen</i>.
          </li>
          <li>
            Probabilities are statistical estimates from historical behaviour,
            not guarantees about any single forecast.
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {DISCLAIMER}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Prototype Data Notice
        </h2>
        <p className="text-sm text-slate-600">
          This prototype runs on a deterministic synthetic Indian monsoon
          dataset (36 regions, ~14 months of paired forecast/observation
          records) so the full pipeline is reproducible end-to-end without
          external dependencies. The same pipeline accepts real NWP/observation
          data (CSV/NetCDF) through the ingestion layer.
        </p>
      </div>
    </div>
  );
}
