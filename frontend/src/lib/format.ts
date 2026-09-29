import type { RiskLevel, Variable } from "./types";

export const pct = (v: number | null | undefined, digits = 0): string =>
  v == null ? "—" : `${(v * 100).toFixed(digits)}%`;

export const RISK_ORDER: RiskLevel[] = [
  "VERY_LOW",
  "LOW",
  "MODERATE",
  "HIGH",
  "VERY_HIGH",
];

export const RISK_COLORS: Record<RiskLevel | "NA", string> = {
  VERY_LOW: "#16a34a",
  LOW: "#84cc16",
  MODERATE: "#f59e0b",
  HIGH: "#f97316",
  VERY_HIGH: "#dc2626",
  NA: "#6b7280",
};

export const RISK_TEXT: Record<RiskLevel | "NA", string> = {
  VERY_LOW: "text-risk-verylow",
  LOW: "text-risk-low",
  MODERATE: "text-risk-moderate",
  HIGH: "text-risk-high",
  VERY_HIGH: "text-risk-veryhigh",
  NA: "text-risk-na",
};

export const RISK_BG: Record<RiskLevel | "NA", string> = {
  VERY_LOW: "bg-risk-verylow",
  LOW: "bg-risk-low",
  MODERATE: "bg-risk-moderate",
  HIGH: "bg-risk-high",
  VERY_HIGH: "bg-risk-veryhigh",
  NA: "bg-risk-na",
};

export const riskLabel = (r: RiskLevel | undefined | null): string =>
  r ? r.replace("_", "-") : "N/A";

export const VARIABLE_LABELS: Record<Variable, string> = {
  rainfall: "Rainfall",
  temperature: "Temperature",
  wind_speed: "Wind Speed",
  pressure: "Pressure",
  humidity: "Humidity",
};

export const VARIABLE_UNITS: Record<Variable, string> = {
  rainfall: "mm",
  temperature: "°C",
  wind_speed: "m/s",
  pressure: "hPa",
  humidity: "%",
};

export const fmtTime = (iso?: string): string => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }) + " IST";
};
