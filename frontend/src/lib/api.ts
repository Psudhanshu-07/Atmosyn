import axios from "axios";
import type {
  Alert,
  AnalyticsError,
  Confidence,
  DashboardKpis,
  DataQuality,
  DataSource,
  Explanation,
  Forecast,
  Health,
  MapConfidenceResponse,
  ModelInfo,
  Region,
  SystemVerificationResponse,
  TenDayResponse,
  TrendPoint,
  Variable,
  VerificationSeriesResponse,
} from "./types";

export const api = axios.create({
  baseURL:
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
    "https://atmosyn.onrender.com/api/v1",
  timeout: 15000,
});

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

api.interceptors.response.use(
  (res) => {
    const contentType = String(res.headers["content-type"] ?? "").toLowerCase();
    if (!contentType.includes("json")) {
      return Promise.reject(
        new ApiError(
          "INVALID_API_RESPONSE",
          "The API returned a non-JSON response. Set VITE_API_BASE_URL to https://atmosyn.onrender.com/api/v1 in Vercel.",
        ),
      );
    }
    return res;
  },
  (error) => {
    const detail = error.response?.data?.detail;
    if (detail && typeof detail === "object" && detail.code) {
      return Promise.reject(
        new ApiError(detail.code, detail.message ?? "Request failed"),
      );
    }
    return Promise.reject(error);
  },
);

export const Api = {
  health: () =>
    api.get<Health>("/health").then((r) => r.data),

  regions: () =>
    api
      .get<{ count: number; regions: Region[] }>("/regions")
      .then((r) => r.data.regions),

  forecast: (regionId: string, leadDay?: number, variable?: Variable) =>
    api
      .get<{ count: number; forecasts: Forecast[] }>("/forecast", {
        params: { region_id: regionId, lead_day: leadDay, variable },
      })
      .then((r) => r.data.forecasts),

  confidence: (regionId: string, leadDay: number, variable: Variable) =>
    api
      .get<Confidence>("/confidence", {
        params: { region_id: regionId, lead_day: leadDay, variable },
      })
      .then((r) => r.data),

  confidence10day: (regionId: string, variable: Variable) =>
    api
      .get<TenDayResponse>("/confidence/10day", {
        params: { region_id: regionId, variable },
      })
      .then((r) => r.data),

  mapConfidence: (leadDay: number, variable: Variable) =>
    api
      .get<MapConfidenceResponse>("/map/confidence", {
        params: { lead_day: leadDay, variable },
      })
      .then((r) => r.data),

  explanation: (predictionId: string) =>
    api
      .get<Explanation>(`/explanation/${predictionId}`)
      .then((r) => r.data),

  analyticsError: (
    regionId: string,
    variable: Variable,
    leadDay?: number,
  ) =>
    api
      .get<AnalyticsError>("/analytics/error", {
        params: { region_id: regionId, variable, lead_day: leadDay },
      })
      .then((r) => r.data),

  analyticsTrends: (regionId: string | undefined, variable: Variable) =>
    api
      .get<{ data: TrendPoint[] }>("/analytics/trends", {
        params: { region_id: regionId, variable },
      })
      .then((r) => r.data.data),

  alerts: (status = "ACTIVE") =>
    api
      .get<{ count: number; alerts: Alert[] }>("/alerts", {
        params: { status },
      })
      .then((r) => r.data.alerts),

  acknowledgeAlert: (alertId: string) =>
    api
      .post(`/alerts/${alertId}/acknowledge`, { acknowledged_by: "operator" })
      .then((r) => r.data),

  models: () =>
    api
      .get<{ models: ModelInfo[] }>("/models")
      .then((r) => r.data.models),

  dataQuality: () =>
    api.get<DataQuality>("/data-quality").then((r) => r.data),

  dashboardKpis: (leadDay: number, variable: Variable) =>
    api
      .get<DashboardKpis>("/dashboard/kpis", {
        params: { lead_day: leadDay, variable },
      })
      .then((r) => r.data),

  forecastVerification: (
    regionId: string,
    variable: Variable,
    leadDay?: number,
    limit = 30,
  ) =>
    api
      .get<VerificationSeriesResponse>("/forecast/verification", {
        params: { region_id: regionId, variable, lead_day: leadDay, limit },
      })
      .then((r) => r.data),

  dataSources: () =>
    api
      .get<{ count: number; sources: DataSource[] }>("/data-sources")
      .then((r) => r.data.sources),

  systemVerification: () =>
    api
      .get<SystemVerificationResponse>("/system-verification")
      .then((r) => r.data),

  gfsStatus: () =>
    api.get<import("./types").GFSStatusResponse>("/gfs/status").then((r) => r.data),

  gfsUpdate: (force = false) =>
    api
      .post<{ outcome: string; message: string; run?: any }>("/gfs/update", null, {
        params: { force, sync_db: true },
      })
      .then((r) => r.data),

  indiaWeatherMap: (leadDay = 1, force = false) =>
    api
      .get<import("./types").IndiaWeatherMapResponse>("/gfs/india-map", {
        params: { lead_day: leadDay, force },
      })
      .then((r) => r.data),
};
