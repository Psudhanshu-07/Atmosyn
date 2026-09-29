"""GET /data-sources — Documented data sources & provenance (PRD §4, §5, §31)."""
from __future__ import annotations

from fastapi import APIRouter
from app.core.schemas import DataSourceOut, DataSourcesResponse

router = APIRouter()

DATA_SOURCES = [
    DataSourceOut(
        id="noaa-nomads-gfs",
        name="NOAA / NCEP GFS 0.25°",
        provider="NOAA / National Centers for Environmental Prediction (NCEP)",
        dataset="Global Forecast System (GFS) 0.25 Degree Gridded Forecast Output",
        purpose="Operational medium-range NWP weather forecasts for Day 1–Day 10 (rainfall, temperature, wind, pressure, humidity).",
        url="https://nomads.ncep.noaa.gov/",
        variables=[
            "Total Precipitation (APCP)",
            "2m Temperature (TMP)",
            "10m U/V Wind Components (UGRD/VGRD)",
            "Surface Pressure (PRES)",
            "2m Relative Humidity (RH)",
        ],
        spatial_resolution="0.25° (~28 km) global latitude-longitude grid",
        temporal_resolution="3-hourly out to 240h (10 days); 4 daily cycles (00, 06, 12, 18 UTC)",
        historical_coverage="Rolling 10-day operational buffer on NOMADS; full archive on NOAA NCEI & AWS Open Data (s3://noaa-gfs-bdp-pds)",
        update_frequency="Every 6 hours (4 times daily)",
        license_terms="Public Domain / Open Data (US Government Work)",
        access_requirements="Free open HTTP / OpenDAP / HTTPS download; no registration required",
        status="OPERATIONAL",
        limitations="Numerical model output (NWP), not an observation. The operational server rate-limits requests and keeps a rolling ~10-day buffer, so the ingestion service caches every cycle locally and applies retention. Integration lives in backend/app/services/gfs/ and is exposed at /api/v1/gfs/*.",
    ),
    DataSourceOut(
        id="noaa-ncei-isd",
        name="NOAA / NCEI Surface Stations",
        provider="NOAA / National Centers for Environmental Information (NCEI)",
        dataset="Integrated Surface Database (ISD) / Global Surface Hourly (CDO)",
        purpose="Ground-truth surface observations for historical error calculation and forecast-observation verification pairing.",
        url="https://www.ncei.noaa.gov/cdo-web/",
        variables=[
            "Precipitation Amount",
            "Dry Bulb Air Temperature",
            "Dew Point Temperature",
            "Wind Speed and Direction",
            "Station Barometric Pressure",
        ],
        spatial_resolution="Point surface weather stations (WMO / ICAO surface synoptic network across India)",
        temporal_resolution="Hourly and sub-hourly reports, aggregated to daily totals/means",
        historical_coverage="1901–present (>120 years archive)",
        update_frequency="Daily updates as synoptic reports arrive",
        license_terms="Public Domain / Open Data",
        access_requirements="Free open access; optional API token for CDO Web Services REST API v2",
        status="OPERATIONAL_READY",
        limitations="Station density in India is concentrated at major airports and metropolitan stations; synoptic transmission delays can affect real-time updates.",
    ),
    DataSourceOut(
        id="ecmwf-copernicus-era5",
        name="Copernicus ERA5 Reanalysis",
        provider="European Centre for Medium-Range Weather Forecasts (ECMWF) / C3S",
        dataset="ERA5 Atmospheric Reanalysis of the Global Climate",
        purpose="Historical atmospheric context, seasonal baselines, synoptic pattern matching, and model backtesting (labeled as Reanalysis, not raw station ground truth).",
        url="https://cds.climate.copernicus.eu/",
        variables=[
            "Total Precipitation",
            "2m Temperature",
            "10m Wind Speed",
            "Mean Sea Level Pressure",
            "500 hPa Geopotential Height",
            "Convective Available Potential Energy (CAPE)",
        ],
        spatial_resolution="0.25° (~31 km) global atmospheric grid, 0.1° land surface grid",
        temporal_resolution="Hourly data globally",
        historical_coverage="1940 to present (near real-time preliminary ERA5T with ~1-5 day latency)",
        update_frequency="Monthly consolidated releases; daily updates for preliminary ERA5T",
        license_terms="Open Access under Copernicus Licence (free for commercial and non-commercial use)",
        access_requirements="Free registration on Copernicus Climate Data Store; CDS API key for Python programmatic access",
        status="REFERENCE",
        limitations="Model reanalysis combining observations with NWP physics — must be explicitly labeled as Reanalysis rather than direct ground-truth station observations.",
    ),
    DataSourceOut(
        id="isro-mosdac-insat",
        name="ISRO MOSDAC Satellite Products",
        provider="Space Applications Centre (SAC), Indian Space Research Organisation (ISRO)",
        dataset="INSAT-3D / INSAT-3DR / INSAT-3DS Meteorological & Rainfall Products",
        purpose="Indian regional geostationary satellite coverage, Hydro-Estimator rainfall (HEM), cloud-top temperatures, and convective storm tracking.",
        url="https://mosdac.gov.in/",
        variables=[
            "Hydro-Estimator Rainfall (HEM)",
            "Quantitative Precipitation Estimation (QPE)",
            "Thermal IR Brightness Temperature (TBB)",
            "Outgoing Longwave Radiation (OLR)",
            "Atmospheric Motion Vectors (AMV)",
        ],
        spatial_resolution="4 km Thermal IR, 1 km Visible; regional coverage over the Indian subcontinent and tropical Indian Ocean",
        temporal_resolution="15-minute to 30-minute rapid scan cycles",
        historical_coverage="2014–present (INSAT-3D/3DR), 2024–present (INSAT-3DS)",
        update_frequency="Near-real-time every 15–30 minutes",
        license_terms="ISRO MOSDAC Data Policy (Free for research, academic, and operational government use)",
        access_requirements="User registration required on MOSDAC portal for OpenDAP/FTP and API token authentication",
        status="AVAILABLE",
        limitations="Satellite rainfall is derived indirectly from cloud-top cooling and requires ground calibration; registration and user credentials required for bulk download.",
    ),
]


@router.get("/data-sources", response_model=DataSourcesResponse)
def get_data_sources():
    """List authoritative data sources with full provenance and access details."""
    return DataSourcesResponse(count=len(DATA_SOURCES), sources=DATA_SOURCES)
