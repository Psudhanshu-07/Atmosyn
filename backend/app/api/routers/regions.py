"""GET /regions and /regions/{region_id} (API contract §5-6)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import Region
from app.core.schemas import RegionOut, RegionsResponse

router = APIRouter()


@router.get("/regions", response_model=RegionsResponse)
def list_regions(
    state: Optional[str] = Query(None, description="Filter by state name"),
    db: Session = Depends(get_db),
):
    q = db.query(Region)
    if state:
        q = q.filter(Region.state.ilike(f"%{state}%"))
    regions = q.order_by(Region.region_id).all()
    return RegionsResponse(
        count=len(regions),
        regions=[
            RegionOut(
                region_id=r.region_id,
                region_name=r.region_name,
                state=r.state,
                latitude=r.latitude,
                longitude=r.longitude,
                elevation=r.elevation,
                coastal=r.coastal,
            )
            for r in regions
        ],
    )


@router.get("/regions/{region_id}", response_model=RegionOut)
def get_region(region_id: str, db: Session = Depends(get_db)):
    r = db.query(Region).filter(Region.region_id == region_id.upper()).first()
    if r is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REGION_NOT_FOUND", "message": f"Region {region_id} was not found"},
        )
    return RegionOut(
        region_id=r.region_id,
        region_name=r.region_name,
        state=r.state,
        latitude=r.latitude,
        longitude=r.longitude,
        elevation=r.elevation,
        coastal=r.coastal,
    )
