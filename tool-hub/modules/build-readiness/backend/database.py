import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Numeric, Integer, text, create_engine,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class BuildReadinessProfile(Base):
    __tablename__ = "build_readiness_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(String, nullable=False)
    website_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    last_indexed_at = Column(DateTime)
    pages_indexed = Column(Integer, default=0)
    chunks_indexed = Column(Integer, default=0)
    videos_indexed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BuildReadinessChunk(Base):
    __tablename__ = "build_readiness_chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), nullable=False)
    source_type = Column(String, nullable=False)  # website | video
    source_url = Column(Text, nullable=False)
    title = Column(Text)
    content = Column(Text, nullable=False)
    embedding = Column(JSONB, nullable=False)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class BuildReadinessCapability(Base):
    __tablename__ = "build_readiness_capabilities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), nullable=False)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    evidence_count = Column(Integer, default=1)
    sample_urls = Column(ARRAY(String), default=list)
    depth_score = Column(Numeric, default=0)
    extracted_at = Column(DateTime, default=datetime.utcnow)


class BuildReadinessVerdict(Base):
    __tablename__ = "build_readiness_verdicts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), nullable=False)
    domain_id = Column(UUID(as_uuid=True))
    domain_name = Column(String, nullable=False)
    track = Column(String, nullable=False)
    market_score = Column(Numeric, nullable=False)
    capability_score = Column(Numeric, nullable=False)
    opportunity_score = Column(Numeric, nullable=False)
    verdict = Column(String, nullable=False)  # GO | CONDITIONAL | NO_GO
    verdict_json = Column(JSONB, nullable=False)
    citations = Column(JSONB, default=list)
    analyzed_at = Column(DateTime, default=datetime.utcnow)


class BuildReadinessJob(Base):
    __tablename__ = "build_readiness_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(String, nullable=False)  # index_website | index_videos | analyze
    status = Column(String, nullable=False, default="queued")
    error = Column(Text)
    progress = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


def run_migrations():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS build_readiness_profiles (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              company_name TEXT NOT NULL,
              website_url TEXT NOT NULL,
              is_active BOOLEAN DEFAULT true,
              last_indexed_at TIMESTAMPTZ,
              pages_indexed INT DEFAULT 0,
              chunks_indexed INT DEFAULT 0,
              videos_indexed INT DEFAULT 0,
              created_at TIMESTAMPTZ DEFAULT now(),
              updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS build_readiness_chunks (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              profile_id UUID NOT NULL,
              source_type TEXT NOT NULL,
              source_url TEXT NOT NULL,
              title TEXT,
              content TEXT NOT NULL,
              embedding JSONB NOT NULL,
              metadata_json JSONB DEFAULT '{}',
              created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS build_readiness_capabilities (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              profile_id UUID NOT NULL,
              category TEXT NOT NULL,
              name TEXT NOT NULL,
              evidence_count INT DEFAULT 1,
              sample_urls TEXT[] DEFAULT '{}',
              depth_score NUMERIC DEFAULT 0,
              extracted_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS build_readiness_verdicts (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              profile_id UUID NOT NULL,
              domain_id UUID,
              domain_name TEXT NOT NULL,
              track TEXT NOT NULL,
              market_score NUMERIC NOT NULL,
              capability_score NUMERIC NOT NULL,
              opportunity_score NUMERIC NOT NULL,
              verdict TEXT NOT NULL,
              verdict_json JSONB NOT NULL,
              citations JSONB DEFAULT '[]',
              analyzed_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS build_readiness_jobs (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              job_type TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              error TEXT,
              progress JSONB DEFAULT '{}',
              created_at TIMESTAMPTZ DEFAULT now(),
              completed_at TIMESTAMPTZ
            )
        """))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
