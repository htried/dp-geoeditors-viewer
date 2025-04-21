from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class EditorData(Base):
    __tablename__ = "editor_data"

    id = Column(Integer, primary_key=True, index=True)
    wiki_db = Column(String)
    project = Column(String)
    country = Column(String)
    country_code = Column(String)
    activity_level = Column(String)
    count_eps = Column(Integer)
    sum_eps = Column(Float)
    count_release_thresh = Column(Integer)
    editors = Column(Integer)
    edits = Column(Integer)
    month = Column(Date)

    def __repr__(self):
        return f"<EditorData(country={self.country}, month={self.month}, editors={self.editors})>"

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 