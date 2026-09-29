import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import { RISK_COLORS, pct, riskLabel } from "../lib/format";
import type { MapConfidenceResponse, MapRegionPoint } from "../lib/types";

const INDIA_CENTER: [number, number] = [22.5, 80];
const DEFAULT_ZOOM = 5;

export function IndiaMap({
  data,
  onRegionClick,
  selectedRegionId,
}: {
  data: MapConfidenceResponse | null;
  onRegionClick: (region: MapRegionPoint) => void;
  selectedRegionId?: string | null;
}) {
  if (!data) return null;
  return (
    <MapContainer
      center={INDIA_CENTER}
      zoom={DEFAULT_ZOOM}
      scrollWheelZoom
      style={{ height: "420px", width: "100%" }}
      className="h-[420px] w-full rounded-lg z-0"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {data.regions.map((r) => {
        const hasData = r.status === "OK" && r.bust_probability != null;
        const color = hasData
          ? RISK_COLORS[(r.risk_level ?? "NA") as keyof typeof RISK_COLORS]
          : RISK_COLORS.NA;
        const isSelected = selectedRegionId === r.region_id;
        return (
          <CircleMarker
            key={r.region_id}
            center={[r.latitude, r.longitude]}
            radius={isSelected ? 12 : 8}
            pathOptions={{
              color: isSelected ? "#0284c7" : color,
              weight: isSelected ? 3 : 1.5,
              fillColor: color,
              fillOpacity: 0.75,
            }}
            eventHandlers={{ click: () => onRegionClick(r) }}
          >
            <Tooltip direction="top" offset={[0, -6]} opacity={1}>
              <div className="text-xs p-1">
                <div className="font-bold text-slate-900 border-b border-slate-200 pb-1">
                  {r.region_name}, {r.state}
                </div>
                <div className="mt-1 text-[11px] text-slate-500 font-medium">
                  Day {data.lead_day} · <span className="capitalize">{data.variable.replace("_", " ")}</span>
                </div>
                <div className="mt-1 space-y-0.5">
                  <div className="flex justify-between gap-3">
                    <span className="text-slate-600">Bust Probability:</span>
                    <b className="text-slate-900">{hasData ? pct(r.bust_probability) : "unavailable"}</b>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-slate-600">AI Reliability:</span>
                    <b className={r.risk_level === "HIGH" || r.risk_level === "VERY_HIGH" ? "text-orange-600" : "text-emerald-700"}>
                      {riskLabel(r.risk_level)} ({hasData ? pct(r.confidence) : "—"})
                    </b>
                  </div>
                  {r.expected_error != null && (
                    <div className="flex justify-between gap-3">
                      <span className="text-slate-600">Expected Error:</span>
                      <b className="text-slate-800">{r.expected_error}</b>
                    </div>
                  )}
                  {r.forecast_value != null && (
                    <div className="flex justify-between gap-3 text-[11px] text-slate-500">
                      <span>NWP Forecast:</span>
                      <span>{r.forecast_value}</span>
                    </div>
                  )}
                </div>
                <div className="mt-1.5 pt-1 border-t border-slate-100 text-[10px] text-sky-700 font-medium">
                  Click to inspect regional factors →
                </div>
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

export function MapLegend() {
  const entries: Array<[string, string, string]> = [
    ["VERY_LOW", "Very Low Risk (0–20%)", "High Reliability"],
    ["LOW", "Low Risk (20–40%)", "Good Reliability"],
    ["MODERATE", "Moderate Risk (40–60%)", "Caution"],
    ["HIGH", "High Risk (60–80%)", "Elevated Uncertainty"],
    ["VERY_HIGH", "Very High Risk (80–100%)", "Low Reliability"],
    ["NA", "No Prediction", "Pending"],
  ];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-slate-50 p-2.5 text-xs text-slate-700 border border-slate-100">
      <span className="font-semibold text-slate-800">Forecast Bust Risk:</span>
      {entries.map(([k, label, note]) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-3.5 w-3.5 rounded-full border border-black/10 shrink-0"
            style={{ backgroundColor: RISK_COLORS[k as keyof typeof RISK_COLORS] }}
            aria-hidden
          />
          <span className="font-medium text-slate-800">{label}</span>
          <span className="text-[10px] text-slate-500">({note})</span>
        </span>
      ))}
    </div>
  );
}
