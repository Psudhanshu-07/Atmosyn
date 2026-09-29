"""Shared pytest fixtures: isolated database + TestClient + seed helper."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))

# Isolated test database BEFORE importing app modules. Absolute path so the
# location is independent of pytest's working directory (and cleanup matches).
os.environ["DATABASE_URL"] = f"sqlite:///{(_ROOT / 'test_forecast_bust.db').as_posix()}"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db():
    yield
    from app.core.database import engine

    engine.dispose()
    p = _ROOT / "test_forecast_bust.db"
    if p.exists():
        try:
            p.unlink()
        except PermissionError:
            pass


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import Base, engine

    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session():
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def seeded_db(client):
    """Run the full seeder once for API tests (may reuse cache)."""
    import importlib

    import seed_database  # noqa: PLC0415

    importlib.reload(seed_database)
    seed_database.create_schema()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        id_map = {r.region_id: r.id for r in db.query(Region).all()}
        seed_database.seed_regions(db)
        id_map = {r.region_id: r.id for r in db.query(Region).all()}
        seed_database.seed_history(db, id_map)
        seed_database._backfill_hist_features(db)
        seed_database.train_models_if_needed()
        seed_database.seed_current_run(db, id_map)
    finally:
        db.close()
    return None


from app.core.models import Region  # noqa: E402  (after env set)
