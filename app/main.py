from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.engine import analyze_area
from app.database import SessionLocal
from app.models import AnalysisResult

from geoalchemy2.shape import from_shape
from shapely.geometry import Point

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AreaRequest(BaseModel):
    lat: float
    lon: float
    radius: int
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
        request.date2_end
    )

    db = SessionLocal()

    point = from_shape(Point(request.lon, request.lat), srid=4326)

    db_result = AnalysisResult(
        latitude=request.lat,
        longitude=request.lon,
        radius=request.radius,
        encroachment_percent=result["encroachment_percent"],
        risk_level=result["risk_level"],
        location=point
    )

    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    db.close()

    return result
