from sqlalchemy import Column, Integer, Float, String
from geoalchemy2 import Geometry
from app.database import Base

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    encroachment_percent = Column(Float)
    risk_level = Column(String)

    area_geom = Column(Geometry(geometry_type='GEOMETRY', srid=4326))

