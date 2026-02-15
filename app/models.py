from sqlalchemy import Column, Integer, Float, String
from geoalchemy2 import Geometry
from app.database import Base

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    latitude = Column(Float)
    longitude = Column(Float)
    radius = Column(Integer)

    encroachment_percent = Column(Float)
    risk_level = Column(String)

    # Store geometry as POINT
    location = Column(Geometry(geometry_type='POINT', srid=4326))
