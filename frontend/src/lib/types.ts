/**
 * API types mirroring the backend contract (API Endpoint.txt).
 */
export type Variable =
  | "rainfall"
  | "temperature"
  | "wind_speed"
  | "pressure"
  | "humidity";

export type RiskLevel =
  | "VERY_LOW"
  | "LOW"
  | "MODERATE"
  | "HIGH"
  | "VERY_HIGH";

export interface Region {
  region_id: string;
  region_name: string;
  state: string;
  latitude: number;
  longitude: number;
  elevation: number;
  coastal: boolean;
}

export interface Forecast {
  region_id: string;
  forecast_run: string;
  valid_time: string;
  lead_day: number;
  variable: Variable;
  value: number;
  unit: string;
  source: string;
}

export interface Confidence {
  region_id: string;
  lead_day: number;
  variable: Variable;
  bust_probability: number;
  confidence_score: number;
  risk_level: RiskLevel;
  expected_error: number;
  forecast_value?: number;
  model_version?: string;
  forecast_run?: string;
  valid_time?: string;
  prediction_id?: string;
}

export interface ConfidenceDay {
  lead_day: number;
  bust_probability: number;
  confidence: number;
  risk_level: RiskLevel;
  expected_error: number;
  forecast_value?: number;
}

export interface TenDayResponse {
  region_id: string;
  region_name: string;
  variable: Variable;
  forecast_run?: string;
  days: ConfidenceDay[];
}

export interface MapRegionPoint {
  region_id: string;
  region_name: string;
  state: string;
  latitude: number;
  longitude: number;
  forecast_value?: number;
  bust_probability?: number;
  confidence?: number;
  risk_level?: RiskLevel;
  expected_error?: number;
  status: "OK" | "NO_PREDICTION" | "STALE_DATA";
}

export interface MapConfidenceResponse {
  lead_day: number;
  variable: Variable;
  forecast_run?: string;
  generated_at?: string;
  data_status: string;
  regions: MapRegionPoint[];
}

export interface Prediction {
  prediction_id: string;
  region_id: string;
  variable: Variable;
  lead_day: number;
  forecast_run?: string;
  valid_time?: string;
  forecast_value: number;
  expected_error: number;
  bust_probability: number;
  confidence_score: number;
  risk_level: RiskLevel;
  model_version: string;
  predicted_at?: string;
}

export interface ExplanationFactor {
  feature: string;
  label: string;
  value: number;
  impact: "HIGH" | "MEDIUM" | "LOW";
  shap_value: number;
  direction: string;
}

export interface Explanation {
  prediction_id: string;
  region_id: string;
  variable: Variable;
  lead_day: number;
  bust_probability: number;
  risk_level: string;
  summary: string;
  explanation: ExplanationFactor[];
  model_version: string;
}

export interface ErrorStatistics {
  mae: number;
  rmse: number;
  bias: number;
  bust_rate: number;
  sample_count: number;
}

export interface AnalyticsError {
  region_id: string;
  variable: Variable;
  lead_day?: number;
  statistics: ErrorStatistics;
}

export interface TrendPoint {
  date: string;
  mae: number;
  bust_rate: number;
}

export interface Alert {
  alert_id: string;
  region_id: string;
  region_name: string;
  alert_type: string;
  variable: Variable;
  lead_day: number;
  bust_probability: number;
  confidence: number;
  risk_level: RiskLevel;
  status: string;
  message: string;
  model_version: string;
  generated_at?: string;
  expires_at?: string;
  disclaimer?: string;
}

export interface ModelInfo {
  model_version: string;
  algorithm: string;
  status: string;
  roc_auc?: number;
  brier_score?: number;
  precision_?: number;
  recall_?: number;
  f1?: number;
  mae?: number;
  rmse?: number;
  trained_from?: string;
  trained_to?: string;
  checksum: string;
}

export interface DataQualitySource {
  source: string;
  status: string;
  last_updated?: string;
  records?: number;
}

export interface DataQuality {
  overall_status: string;
  sources: DataQualitySource[];
  warnings: string[];
}

export interface DashboardKpis {
  regions_monitored: number;
  high_risk_regions: number;
  avg_confidence: number;
  highest_risk_lead_day: number;
  data_quality: number;
  forecast_run?: string;
  data_status: string;
}

export interface Health {
  status: string;
  service: string;
  version: string;
  database: string;
  ml_service: string;
  active_model?: string;
  timestamp: string;
}

export interface DataSource {
  id: string;
  name: string;
  provider: string;
  dataset: string;
  purpose: string;
  url: string;
  variables: string[];
  spatial_resolution: string;
  temporal_resolution: string;
  historical_coverage: string;
  update_frequency: string;
  license_terms: string;
  access_requirements: string;
  status: string;
  limitations: string;
}

export interface SystemVerificationItem {
  component: string;
  category: "Data" | "ML" | "API" | "Database" | "System";
  status: "PASS" | "FAIL" | "WARNING";
  details: string;
  checked_at: string;
}

export interface SystemVerificationResponse {
  overall_status: "PASS" | "DEGRADED" | "FAIL";
  checked_at: string;
  items: SystemVerificationItem[];
}

export interface VerificationPair {
  valid_time: string;
  forecast_run: string;
  lead_day: number;
  forecast_value: number;
  observed_value: number;
  absolute_error: number;
  signed_error: number;
  bust: boolean;
  bust_threshold: number;
  unit: string;
}

export interface VerificationSeriesResponse {
  region_id: string;
  region_name: string;
  variable: Variable;
  count: number;
  pairs: VerificationPair[];
}

export interface GFSStatusResponse {
  provider: string;
  source_url: string;
  api_key_required: boolean;
  data_type: string;
  disclaimer: string;
  scheduler_running: boolean;
  update_interval_minutes: number;
  last_check_at?: string;
  last_check_outcome?: string;
  stored_runs: number;
  active_run?: {
    model: string;
    source: string;
    source_label: string;
    data_type: string;
    run_date: string;
    cycle: string;
    run_time: string;
    status: string;
    is_active: boolean;
    files_valid: number;
    files_total: number;
    discovered_at?: string;
    activated_at?: string;
    processed_at?: string;
  };
}

export interface StateWeatherPoint {
  state_code: string;
  state_name: string;
  capital: string;
  latitude: number;
  longitude: number;
  lead_day: number;
  temperature: number | null;
  rainfall: number | null;
  rain_probability: number | null;
  wind_speed: number | null;
  humidity: number | null;
  pressure: number | null;
  weather_condition: string;
  forecast_confidence: number;
  confidence_level: "HIGH" | "MODERATE" | "LOW" | "NO_DATA";
  confidence_color: string;
}

export interface IndiaWeatherMapResponse {
  model: string;
  model_version: string;
  source: string;
  source_label: string;
  run_date: string;
  cycle: string;
  run_time: string;
  valid_time: string;
  lead_day: number;
  last_updated: string;
  is_cached: boolean;
  status_note: string;
  disclaimer: string;
  states_count: number;
  states: StateWeatherPoint[];
}


