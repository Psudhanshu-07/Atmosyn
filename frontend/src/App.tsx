import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { DashboardPage } from "./pages/Dashboard";
import { IndiaWeatherMapPage } from "./pages/IndiaWeatherMap";
import { ForecastMapPage } from "./pages/ForecastMap";
import { BustDetectionPage } from "./pages/BustDetection";
import { RegionDetailsPage } from "./pages/RegionDetails";
import { AnalyticsPage } from "./pages/Analytics";
import { AlertsPage } from "./pages/Alerts";
import { SystemHealthPage } from "./pages/SystemHealth";
import { MethodologyPage } from "./pages/Methodology";
import { DataSourcesPage } from "./pages/DataSources";
import { SystemVerificationPage } from "./pages/SystemVerification";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />} path="/">
          <Route index element={<DashboardPage />} />
          <Route path="india-map" element={<IndiaWeatherMapPage />} />
          <Route path="map" element={<ForecastMapPage />} />
          <Route path="detection" element={<BustDetectionPage />} />
          <Route path="region" element={<RegionDetailsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="sources" element={<DataSourcesPage />} />
          <Route path="verification" element={<SystemVerificationPage />} />
          <Route path="system" element={<SystemHealthPage />} />
          <Route path="methodology" element={<MethodologyPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
