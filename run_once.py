# run_once.py
from app.database import engine
from app.models import Base

Base.metadata.create_all(bind=engine)
