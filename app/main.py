from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import HTTPException

from app.engine import analyze_area
from app.database import SessionLocal
from app.models import AnalysisResult

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, shape

from typing import Dict, Optional

from fastapi.responses import FileResponse
import os
from datetime import datetime

from app.report_utils import download_and_save_image, generate_pdf_report

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

    # Save DB row first
    db_result = AnalysisResult(
        encroachment_percent=result["encroachment_percent"],
        risk_level=result["risk_level"],
        area_geom=db_geom
    )

    db.add(db_result)
    db.commit()
    db.refresh(db_result)

    analysis_id = db_result.id

    # -------------------------
    # Generate report folder
    # -------------------------
    folder = f"reports/{analysis_id}"
    os.makedirs(folder, exist_ok=True)

    # Download thumbnails once
    t0_path = download_and_save_image(result["t0_thumb"], folder, "t0.png")
    t1_path = download_and_save_image(result["t1_thumb"], folder, "t1.png")
    enc_path = download_and_save_image(result["encroach_thumb"], folder, "encroachment.png")

    metadata = {
        "date1_start": request.date1_start,
        "date1_end": request.date1_end,
        "date2_start": request.date2_start,
        "date2_end": request.date2_end,
        "generated_on": datetime.utcnow()
    }

    # Generate PDF
    pdf_path = generate_pdf_report(folder, result, metadata)

    # Update DB with file paths
    db_result.report_path = pdf_path
    db_result.t0_image_path = t0_path
    db_result.t1_image_path = t1_path
    db_result.enc_image_path = enc_path

    db.commit()
    db.close()

    return {
        **result,
        "report_id": analysis_id
    }

@app.get("/report/{report_id}")
def download_report(report_id: int):

    db = SessionLocal()

    report = db.query(AnalysisResult).filter(
        AnalysisResult.id == report_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    db.close()

    return FileResponse(
        report.report_path,
        media_type="application/pdf",
        filename=f"urbaneye_report_{report_id}.pdf"
    )

