import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class VideoScraperJob(Base):
    __tablename__ = "video_scraper_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url = Column(Text, nullable=False)
    source_type = Column(String)
    status = Column(String, nullable=False, default="queued")
    error = Column(Text)
    title = Column(String)
    channel_or_author = Column(String)
    duration_seconds = Column(Integer)
    thumbnail_url = Column(Text)
    transcript = Column(Text)
    transcript_source = Column(String)
    summary_json = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
