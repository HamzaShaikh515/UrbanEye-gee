import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Generator, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from geoalchemy2.shape import from_shape
from pydantic import BaseModel
from shapely.geometry import Point, shape
from tenacity import retry, stop_after_attempt, wait_fixed

from app.database import SessionLocal, engine
from app.engine import analyze_area
from app.models import AnalysisResult, Base
from app.report_utils import download_and_save_image, generate_pdf_report


# ---------------------------------------------------------------------------
# In-memory job store  { job_id: { status, result, error } }
# ---------------------------------------------------------------------------
jobs: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@retry(wait=wait_fixed(2), stop=stop_after_attempt(10))
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up — creating database tables if they do not exist…")
    init_db()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="UrbanEye GEE API", lifespan=lifespan)

# TODO: restrict allow_origins to your front-end domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class AreaRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius: Optional[int] = None
    polygon: Optional[Dict] = None

    date1_start: str
    date1_end: str
    date2_start: str
    date2_end: str


# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
def run_analysis(job_id: str, request: AreaRequest) -> None:
    """Heavy GEE analysis — runs in a background thread."""
    jobs[job_id]["status"] = "processing"

    db = SessionLocal()
    try:
        result = analyze_area(
            request.lat,
            request.lon,
            request.radius,
            request.date1_start,
            request.date1_end,
            request.date2_start,
            request.date2_end,
            request.polygon,
        )

        if request.polygon:
            shapely_geom = shape(request.polygon)
        elif request.lat is not None and request.lon is not None:
            shapely_geom = Point(request.lon, request.lat)
        else:
            raise ValueError("Either polygon or lat/lon must be provided.")

        db_result = AnalysisResult(
            encroachment_percent=result["encroachment_percent"],
            risk_level=result["risk_level"],
            area_geom=from_shape(shapely_geom, srid=4326),
        )
        db.add(db_result)
        db.commit()
        db.refresh(db_result)

        analysis_id = db_result.id
        folder = f"reports/{analysis_id}"
        os.makedirs(folder, exist_ok=True)

        t0_path  = download_and_save_image(result["t0_thumb"],      folder, "t0.png")
        t1_path  = download_and_save_image(result["t1_thumb"],      folder, "t1.png")
        enc_path = download_and_save_image(result["encroach_thumb"], folder, "encroachment.png")

        metadata = {
            "date1_start":  request.date1_start,
            "date1_end":    request.date1_end,
            "date2_start":  request.date2_start,
            "date2_end":    request.date2_end,
            "generated_on": datetime.now(timezone.utc),
        }
        pdf_path = generate_pdf_report(folder, result, metadata)

        db_result.report_path   = pdf_path
        db_result.t0_image_path = t0_path
        db_result.t1_image_path = t1_path
        db_result.enc_image_path = enc_path
        db.commit()

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {**result, "report_id": analysis_id}

    except Exception as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"]  = str(exc)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/analyze", status_code=202)
def analyze(request: AreaRequest, background_tasks: BackgroundTasks):
    """Validate the request, queue an analysis job, and return a job_id immediately."""
    if request.polygon is None and (request.lat is None or request.lon is None):
        raise HTTPException(
            status_code=422,
            detail="Provide either 'polygon' or both 'lat' and 'lon'.",
        )
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "result": None, "error": None}
    background_tasks.add_task(run_analysis, job_id, request)
    return {"job_id": job_id, "status": "queued"}


@app.get("/job/{job_id}")
def get_job(job_id: str):
    """Poll the status of a queued / running / completed job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, **job}


@app.get("/report/{report_id}")
def download_report(report_id: int, db=Depends(get_db)):
    """Download the generated PDF report for a completed analysis."""
    report = db.query(AnalysisResult).filter(AnalysisResult.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    if not report.report_path or not os.path.exists(report.report_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk.")
    return FileResponse(
        report.report_path,
        media_type="application/pdf",
        filename=f"urbaneye_report_{report_id}.pdf",
    )