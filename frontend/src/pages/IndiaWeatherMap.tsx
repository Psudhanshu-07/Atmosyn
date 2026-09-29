import { useCallback, useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { PathOptions, Layer } from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  Clock,
  CloudFog,
  CloudRain,
  CloudSun,
  Droplets,
  Gauge,
  Info,
  RefreshCw,
  ShieldCheck,
  Sun,
  Wind,
} from "lucide-react";

import { Api } from "../lib/api";
import { fmtTime } from "../lib/format";
import type {
  IndiaWeatherMapResponse,
  MapConfidenceResponse,
  StateWeatherPoint,
} from "../lib/types";
import { ErrorCard, LoadingCard } from "../components/LoadingError";

interface StateGeoProperties {
  ST_NM: string;
}

function toReliabilityMap(
  response: MapConfidenceResponse,
  leadDay: number,
): IndiaWeatherMapResponse {
  const forecastRun = response.forecast_run ?? new Date().toISOString();
  const confidenceColor = (confidence: number | undefined) => {
    if (confidence === undefined) return "#94A3B8";
    if (confidence >= 0.8) return "#0b8e75";
    if (confidence >= 0.6) return "#d99b18";
    return "#d84a4a";
  };

  return {
    model: "ATMOSYN Reliability",
    model_version: "Stored prediction data",
    source: "ATMOSYN prediction database",
    source_label: "ATMOSYN Forecast Reliability",
    run_date: forecastRun.slice(0, 10),
    cycle: forecastRun.slice(11, 13) || "--",
    run_time: forecastRun,
    valid_time: new Date(Date.parse(forecastRun) + leadDay * 86400000).toISOString(),
    lead_day: leadDay,
    last_updated: response.generated_at ?? forecastRun,
    is_cached: false,
    status_note:
      "GFS data is unavailable. Showing stored regional forecast-reliability estimates; weather details are not available in this view.",
    disclaimer:
      "Forecast values and confidence are application estimates from stored prediction data, not live GFS output, observations, or an official weather forecast or warning.",
    states_count: response.regions.length,
    states: response.regions.map((region): StateWeatherPoint => {
      const confidence = region.confidence;
      const confidenceScore = confidence === undefined ? 0 : Math.round(confidence * 100);
      return {
        state_code: region.region_id,
        state_name: region.state,
        capital: region.region_name,
        latitude: region.latitude,
        longitude: region.longitude,
        lead_day: leadDay,
        temperature: response.variable === "temperature" ? region.forecast_value ?? null : null,
        rainfall: null,
        rain_probability: null,
        wind_speed: null,
        humidity: null,
        pressure: null,
        weather_condition: "Forecast reliability estimate",
        forecast_confidence: confidenceScore,
        confidence_level:
          confidence === undefined
            ? "NO_DATA"
            : confidence >= 0.8
              ? "HIGH"
              : confidence >= 0.6
                ? "MODERATE"
                : "LOW",
        confidence_color: confidenceColor(confidence),
      };
    }),
  };
}

export function IndiaWeatherMapPage() {
  const [leadDay, setLeadDay] = useState<number>(1);
  const [data, setData] = useState<IndiaWeatherMapResponse | null>(null);
  const [geoJsonData, setGeoJsonData] = useState<FeatureCollection<Geometry, StateGeoProperties> | null>(null);
  const [selectedState, setSelectedState] = useState<StateWeatherPoint | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch GeoJSON once
  useEffect(() => {
    fetch("/geo/india-states.geojson")
      .then((res) => {
        if (!res.ok) throw new Error("Could not load India states GeoJSON");
        return res.json();
      })
      .then((geo) => setGeoJsonData(geo))
      .catch((err) => console.error("GeoJSON error:", err));
  }, []);

  // Fetch Weather Map data for selected lead day
  const loadWeatherMap = useCallback(async (day: number, force = false) => {
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      let res: IndiaWeatherMapResponse;
      try {
        res = await Api.indiaWeatherMap(day, force);
      } catch {
        const reliability = await Api.mapConfidence(day, "temperature");
        if (reliability.regions.length === 0) throw new Error("No regional forecast data is available.");
        res = toReliabilityMap(reliability, day);
      }
      setData(res);
      // Update selected state if already chosen
      setSelectedState((prev) => {
        if (!prev) {
          // Default select Delhi or Maharashtra for immediate visibility on desktop
          return res.states.find((s) => s.state_name === "Delhi") || res.states[0] || null;
        }
        return res.states.find((s) => s.state_name === prev.state_name) || res.states[0] || null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load India weather map");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadWeatherMap(leadDay);
  }, [leadDay, loadWeatherMap]);

  // Map state name to weather point for quick lookup
  const stateMap = useMemo(() => {
    const map = new Map<string, StateWeatherPoint>();
    if (data?.states) {
      for (const s of data.states) {
        map.set(s.state_name.toLowerCase().trim(), s);
      }
    }
    return map;
  }, [data]);

  // Leaflet polygon style function
  const styleFeature = useCallback(
    (feature?: Feature<Geometry, StateGeoProperties>): PathOptions => {
      if (!feature || !feature.properties) {
        return {
          fillColor: "#94A3B8",
          weight: 1,
          opacity: 0.8,
          color: "#FFFFFF",
          fillOpacity: 0.65,
        };
      }

      const stName = feature.properties.ST_NM?.toLowerCase().trim();
      const stateWeather = stateMap.get(stName);
      const isSelected = selectedState && selectedState.state_name.toLowerCase().trim() === stName;

      const color = stateWeather ? stateWeather.confidence_color : "#94A3B8";

      return {
        fillColor: color,
        weight: isSelected ? 2.5 : 1,
        opacity: 1,
        color: isSelected ? "#0F172A" : "#FFFFFF",
        fillOpacity: isSelected ? 0.85 : 0.65,
      };
    },
    [stateMap, selectedState],
  );

  // GeoJSON interaction handlers
  const onEachFeature = useCallback(
    (feature: Feature<Geometry, StateGeoProperties>, layer: Layer) => {
      const stName = feature.properties.ST_NM;
      const weather = stateMap.get(stName.toLowerCase().trim());

      // Bind tooltip
      const tooltipContent = weather
        ? `<div class="p-1 text-xs">
            <div class="font-bold text-slate-900">${stName}</div>
            <div class="text-slate-600 mt-0.5">${weather.weather_condition} · ${weather.temperature ?? "--"}°C</div>
            <div class="mt-1 flex items-center gap-1 font-semibold" style="color: ${weather.confidence_color}">
              ● ${weather.forecast_confidence}% Confidence (${weather.confidence_level})
            </div>
           </div>`
        : `<div class="p-1 text-xs font-semibold">${stName} (No Data)</div>`;

      layer.bindTooltip(tooltipContent, {
        sticky: true,
        direction: "auto",
        className: "custom-leaflet-tooltip bg-white shadow-md rounded-lg border border-slate-200 text-slate-800",
      });

      layer.on({
        click: () => {
          if (weather) {
            setSelectedState(weather);
          } else {
            setSelectedState({
              state_code: "--",
              state_name: stName,
              capital: "Unknown",
              latitude: 20.0,
              longitude: 80.0,
              lead_day: leadDay,
              temperature: null,
              rainfall: null,
              rain_probability: null,
              wind_speed: null,
              humidity: null,
              pressure: null,
              weather_condition: "No Data Available",
              forecast_confidence: 0,
              confidence_level: "NO_DATA",
              confidence_color: "#94A3B8",
            });
          }
        },
        mouseover: (e) => {
          const l = e.target;
          l.setStyle({
            weight: 2,
            color: "#1E293B",
            fillOpacity: 0.85,
          });
        },
        mouseout: (e) => {
          const l = e.target;
          const isSelected = selectedState && selectedState.state_name.toLowerCase().trim() === stName.toLowerCase().trim();
          l.setStyle({
            weight: isSelected ? 2.5 : 1,
            color: isSelected ? "#0F172A" : "#FFFFFF",
            fillOpacity: isSelected ? 0.85 : 0.65,
          });
        },
      });
    },
    [stateMap, selectedState, leadDay],
  );

  const getWeatherIcon = (cond: string) => {
    const c = cond.toLowerCase();
    if (c.includes("heavy rain") || c.includes("rain") || c.includes("shower")) {
      return <CloudRain className="text-sky-500" size={28} />;
    }
    if (c.includes("fog") || c.includes("mist")) {
      return <CloudFog className="text-slate-400" size={28} />;
    }
    if (c.includes("overcast") || c.includes("cloud")) {
      return <CloudSun className="text-amber-500" size={28} />;
    }
    return <Sun className="text-amber-500" size={28} />;
  };

  return (
    <div className="space-y-4">
      {/* Top Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">India Weather Map</h1>
            <span className="rounded bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800 uppercase tracking-wide">
              {data?.model === "GFS" ? "NOAA GFS 0.25°" : "Forecast Reliability"}
            </span>
            {data?.is_cached ? (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                Cached Data
              </span>
            ) : data?.model === "GFS" ? (
              <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                Live Forecast
              </span>
            ) : (
              <span className="rounded bg-teal-100 px-2 py-0.5 text-[10px] font-semibold text-teal-800">
                Reliability Fallback
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Medium-range forecast reliability across monitored regions in India.
          </p>
        </div>

        {/* Lead Day selector + Refresh button */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm text-xs font-semibold">
            {[1, 2, 3, 4, 5].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setLeadDay(d)}
                className={`rounded px-2.5 py-1 transition-all cursor-pointer ${
                  leadDay === d ? "bg-sky-600 text-white shadow-xs" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Day {d}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => loadWeatherMap(leadDay, true)}
            disabled={refreshing || loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Status or Fallback Alert */}
      {data?.status_note && (
        <div
          className={`flex items-center justify-between rounded-lg px-3.5 py-2 text-xs border ${
            data.is_cached
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-sky-100 bg-sky-50/70 text-sky-900"
          }`}
        >
          <div className="flex items-center gap-2">
            <Info size={14} className="shrink-0" />
            <span>
              {data.status_note} · Run: <b>{data.run_date} {data.cycle} UTC</b> · Valid:{" "}
              <b>{fmtTime(data.valid_time)}</b>
            </span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500">
            <Clock size={12} />
            <span>Last Updated: {fmtTime(data.last_updated)}</span>
          </div>
        </div>
      )}

      {loading && <LoadingCard label="Loading India Weather Map..." />}
      {error && <ErrorCard title="Map error" message={error} onRetry={() => loadWeatherMap(leadDay)} />}

      {!loading && !error && data && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Main Map Canvas (8 cols on lg) */}
          <div className="lg:col-span-8 flex flex-col space-y-3">
            <div className="relative h-[560px] w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sm">
              {geoJsonData ? (
                <MapContainer
                  center={[22.5, 82.5]}
                  zoom={5}
                  minZoom={4}
                  maxZoom={7}
                  scrollWheelZoom={true}
                  className="h-full w-full z-0"
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <GeoJSON
                    key={`geojson-${leadDay}-${data.run_date}-${data.cycle}`}
                    data={geoJsonData}
                    style={styleFeature}
                    onEachFeature={onEachFeature}
                  />
                </MapContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-slate-500">
                  Loading boundary GeoJSON...
                </div>
              )}

              {/* Floating Confidence Legend on Map */}
              <div className="absolute bottom-3 left-3 z-[1000] rounded-lg border border-slate-200/90 bg-white/95 p-3 shadow-md backdrop-blur-xs text-xs">
                <div className="text-[11px] font-bold text-slate-700 uppercase tracking-wide mb-1.5">
                  Forecast Confidence
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-emerald-500 shrink-0" />
                    <span className="font-semibold text-slate-800">High (80–100%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-amber-500 shrink-0" />
                    <span className="font-semibold text-slate-800">Moderate (60–79%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-rose-500 shrink-0" />
                    <span className="font-semibold text-slate-800">Low (0–59%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-slate-400 shrink-0" />
                    <span className="text-slate-600">No Data</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Explanatory disclaimer banner */}
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] text-slate-600 leading-relaxed shadow-xs flex items-start gap-2">
              <ShieldCheck size={16} className="text-sky-600 shrink-0 mt-0.5" />
              <div>
                <b>Application-Estimated Forecast Confidence:</b> Confidence scores reflect NWP medium-range forecast reliability based on model lead-time error growth, data cycle freshness, and atmospheric stability. This is an advisory decision-support metric and <b>not an official forecast accuracy or IMD warning</b>.
              </div>
            </div>
          </div>

          {/* Right-Hand State Details Panel (4 cols on lg) */}
          <div className="lg:col-span-4 flex flex-col space-y-4">
            {selectedState ? (
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                {/* State Title Header */}
                <div className="flex items-start justify-between border-b border-slate-100 pb-3">
                  <div>
                    <span className="font-mono text-[10px] font-bold text-sky-700 bg-sky-50 px-2 py-0.5 rounded uppercase">
                      {selectedState.state_code}
                    </span>
                    <h2 className="text-lg font-bold text-slate-900 mt-1">{selectedState.state_name}</h2>
                    <p className="text-xs text-slate-500">Representative Capital: {selectedState.capital}</p>
                  </div>
                  <div className="text-right">
                    <span
                      className="inline-block rounded-full px-2.5 py-0.5 text-xs font-bold"
                      style={{
                        backgroundColor: `${selectedState.confidence_color}20`,
                        color: selectedState.confidence_color,
                      }}
                    >
                      {selectedState.confidence_level} CONFIDENCE
                    </span>
                    <div className="text-xs font-mono font-bold text-slate-800 mt-1">
                      {selectedState.forecast_confidence}% Score
                    </div>
                  </div>
                </div>

                {/* Primary Condition & Temp Banner */}
                <div className="flex items-center justify-between rounded-xl bg-gradient-to-br from-slate-50 to-sky-50/50 p-4 border border-slate-100">
                  <div className="flex items-center gap-3">
                    {getWeatherIcon(selectedState.weather_condition)}
                    <div>
                      <div className="text-sm font-bold text-slate-900">{selectedState.weather_condition}</div>
                      <div className="text-xs text-slate-500">Lead Day {selectedState.lead_day} Forecast</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-black text-slate-900">
                      {selectedState.temperature !== null ? `${selectedState.temperature}°C` : "--"}
                    </div>
                    <div className="text-[11px] text-slate-500">Surface Temp (2m)</div>
                  </div>
                </div>

                {/* Confidence Bar */}
                <div className="space-y-1.5 rounded-lg bg-slate-50 p-3 border border-slate-100">
                  <div className="flex justify-between text-xs">
                    <span className="font-semibold text-slate-700">Forecast Confidence</span>
                    <span className="font-bold" style={{ color: selectedState.confidence_color }}>
                      {selectedState.forecast_confidence}/100
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className="h-full transition-all duration-500"
                      style={{
                        width: `${selectedState.forecast_confidence}%`,
                        backgroundColor: selectedState.confidence_color,
                      }}
                    />
                  </div>
                  <div className="text-[10px] text-slate-500 flex justify-between pt-0.5">
                    <span>Low (&lt;60%)</span>
                    <span>Moderate (60-79%)</span>
                    <span>High (80-100%)</span>
                  </div>
                </div>

                {/* Meteorological Metrics Grid */}
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  {/* Rain Probability */}
                  <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-2xs">
                    <div className="flex items-center gap-1.5 text-slate-500 font-semibold mb-1">
                      <Droplets size={14} className="text-sky-500" />
                      <span>Rain Probability</span>
                    </div>
                    <div className="text-base font-bold text-slate-900">
                      {selectedState.rain_probability !== null ? `${selectedState.rain_probability}%` : "--"}
                    </div>
                    <div className="text-[10px] text-slate-400">Precipitation likelihood</div>
                  </div>

                  {/* Rainfall Amount */}
                  <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-2xs">
                    <div className="flex items-center gap-1.5 text-slate-500 font-semibold mb-1">
                      <CloudRain size={14} className="text-blue-500" />
                      <span>Rainfall (24h)</span>
                    </div>
                    <div className="text-base font-bold text-slate-900">
                      {selectedState.rainfall !== null ? `${selectedState.rainfall} mm` : "--"}
                    </div>
                    <div className="text-[10px] text-slate-400">Liquid accumulation</div>
                  </div>

                  {/* Wind Speed */}
                  <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-2xs">
                    <div className="flex items-center gap-1.5 text-slate-500 font-semibold mb-1">
                      <Wind size={14} className="text-teal-500" />
                      <span>Wind Speed (10m)</span>
                    </div>
                    <div className="text-base font-bold text-slate-900">
                      {selectedState.wind_speed !== null ? `${selectedState.wind_speed} km/h` : "--"}
                    </div>
                    <div className="text-[10px] text-slate-400">Surface vector speed</div>
                  </div>

                  {/* Humidity */}
                  <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-2xs">
                    <div className="flex items-center gap-1.5 text-slate-500 font-semibold mb-1">
                      <Droplets size={14} className="text-indigo-500" />
                      <span>Relative Humidity</span>
                    </div>
                    <div className="text-base font-bold text-slate-900">
                      {selectedState.humidity !== null ? `${selectedState.humidity}%` : "--"}
                    </div>
                    <div className="text-[10px] text-slate-400">2m atmospheric moisture</div>
                  </div>

                  {/* Surface Pressure */}
                  <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-2xs col-span-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-slate-500 font-semibold">
                        <Gauge size={14} className="text-purple-500" />
                        <span>Surface Pressure</span>
                      </div>
                      <div className="text-sm font-bold text-slate-900">
                        {selectedState.pressure !== null ? `${selectedState.pressure} hPa` : "--"}
                      </div>
                    </div>
                  </div>
                </div>

                {/* State Metadata Footer */}
                <div className="rounded-lg bg-slate-50 p-2.5 text-[11px] text-slate-500 border border-slate-100 space-y-1">
                  <div className="flex justify-between">
                    <span>Coordinates:</span>
                    <span className="font-mono text-slate-700">
                      {selectedState.latitude.toFixed(2)}°N, {selectedState.longitude.toFixed(2)}°E
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>NWP Source:</span>
                    <span className="text-slate-700 font-medium">{data.source_label}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Forecast Model Run:</span>
                    <span className="font-mono text-slate-700">{data.run_date} {data.cycle} UTC</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-xs text-slate-500">
                Click any Indian state or union territory on the map to inspect weather parameters and confidence.
              </div>
            )}

            {/* Quick State Selector dropdown for rapid access */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-2">
                Quick Jump to State / UT:
              </label>
              <select
                value={selectedState?.state_name ?? ""}
                onChange={(e) => {
                  const s = data.states.find((x) => x.state_name === e.target.value);
                  if (s) setSelectedState(s);
                }}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-800 focus:border-sky-500 focus:outline-hidden"
              >
                {data.states.map((s) => (
                  <option key={s.state_name} value={s.state_name}>
                    {s.state_name} ({s.temperature !== null ? `${s.temperature}°C` : "--"} · {s.confidence_level})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
