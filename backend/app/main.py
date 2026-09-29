"""FastAPI application factory and router wiring (Arctitcture.txt §16)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.api.routers import (
    alerts,
    analytics,
    confidence,
    data_quality,
    data_sources,
    forecast,
    gfs,
    health,
    models,
    predict,
    regions,
    verification,
)

DESCRIPTION = """
**BUSTRA — AI-Based Forecast Bust Detection and Confidence Mapping System**

Problem Statement 26079 — MoES / NCMRWF

This API is an *AI-derived forecast reliability layer* over medium-range NWP
forecasts. It does **not** replace or constitute an official weather forecast
or warning.

Core flow: NWP forecast → historical error → ML bust detection → calibrated
bust probability → confidence → SHAP explanation → map/analytics.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup for prototype convenience (prod: Alembic).
    Base.metadata.create_all(bind=engine)

    # Optional: keep GFS data fresh in the background. Off unless
    # GFS_AUTO_UPDATE=1 is set, so tests and CI never hit the network.
    scheduler = None
    if settings.gfs_auto_update:
        from app.services.gfs.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="BUSTRA API",
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = settings.api_prefix
    app.include_router(health.router, prefix=api, tags=["Health"])
    app.include_router(regions.router, prefix=api, tags=["Regions"])
    app.include_router(forecast.router, prefix=api, tags=["Forecast"])
    app.include_router(confidence.router, prefix=api, tags=["Confidence"])
    app.include_router(predict.router, prefix=api, tags=["Prediction"])
    app.include_router(analytics.router, prefix=api, tags=["Analytics"])
    app.include_router(alerts.router, prefix=api, tags=["Alerts"])
    app.include_router(models.router, prefix=api, tags=["Models"])
    app.include_router(data_quality.router, prefix=api, tags=["Data Quality"])
    app.include_router(data_sources.router, prefix=api, tags=["Data Sources"])
    app.include_router(verification.router, prefix=api, tags=["System Verification"])
    app.include_router(gfs.router, prefix=api, tags=["GFS (NOAA/NCEP NOMADS)"])

    return app


app = create_app()
