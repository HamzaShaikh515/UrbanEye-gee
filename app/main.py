from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.engine import analyze_area
from app.database import SessionLocal
from app.models import AnalysisResult

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, shape

from typing import Dict, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AreaRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius: Optional[int] = None
    polygon: Optional[Dict] = None

    date1_start: str
    date1_end: str
    date2_start: str
    date2_end: str


@app.post("/analyze")
def analyze(request: AreaRequest):

    result = analyze_area(
        request.lat,
        request.lon,
        request.radius,
        request.date1_start,
        request.date1_end,
        request.date2_start,
        request.date2_end,
        request.polygon
    )

    db = SessionLocal()

    if request.polygon:
        shapely_geom = shape(request.polygon)
    elif request.lat is not None and request.lon is not None:
        shapely_geom = Point(request.lon, request.lat)
    else:
        raise ValueError("Either polygon or lat/lon must be provided")

    db_geom = from_shape(shapely_geom, srid=4326)

    db_result = AnalysisResult(
        encroachment_percent=result["encroachment_percent"],
        risk_level=result["risk_level"],
        area_geom=db_geom
    )

    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    db.close()

    return result
