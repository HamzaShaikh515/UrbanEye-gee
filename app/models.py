from sqlalchemy import Column, Integer, Float, String, DateTime
from geoalchemy2 import Geometry
from app.database import Base
from datetime import datetime

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    encroachment_percent = Column(Float)
    risk_level = Column(String)

    area_geom = Column(Geometry("GEOMETRY", srid=4326))

    report_path = Column(String)
    t0_image_path = Column(String)
    t1_image_path = Column(String)
    enc_image_path = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)