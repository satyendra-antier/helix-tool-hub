import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import create_engine

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
    is_batch = Column(Boolean, default=False)
    progress_json = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    items = relationship(
        "VideoScraperItem",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="VideoScraperItem.sort_order",
    )


class VideoScraperItem(Base):
    __tablename__ = "video_scraper_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("video_scraper_jobs.id", ondelete="CASCADE"), nullable=False)
    video_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
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

    job = relationship("VideoScraperJob", back_populates="items")


MIGRATIONS = """
ALTER TABLE video_scraper_jobs
  ADD COLUMN IF NOT EXISTS is_batch BOOLEAN DEFAULT false;
ALTER TABLE video_scraper_jobs
  ADD COLUMN IF NOT EXISTS progress_json JSONB;

CREATE TABLE IF NOT EXISTS video_scraper_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES video_scraper_jobs(id) ON DELETE CASCADE,
  video_url TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  title TEXT,
  channel_or_author TEXT,
  duration_seconds INT,
  thumbnail_url TEXT,
  transcript TEXT,
  transcript_source TEXT,
  summary_json JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_video_scraper_items_job_id ON video_scraper_items(job_id);
"""


def run_migrations() -> None:
    with engine.begin() as conn:
        conn.execute(text(MIGRATIONS))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
