import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, Boolean, DateTime, Numeric, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class MarketDepthDomain(Base):
    __tablename__ = "market_depth_domains"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    track = Column(String, nullable=False)
    keywords = Column(ARRAY(String), nullable=False)
    active = Column(Boolean, default=True)


class MarketDepthSnapshot(Base):
    __tablename__ = "market_depth_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id = Column(UUID(as_uuid=True))
    snapshot_batch_id = Column(UUID(as_uuid=True))
    raw_evidence = Column(JSONB, nullable=False)
    component_scores = Column(JSONB, nullable=False)
    composite_score = Column(Numeric, nullable=False)
    weights_used = Column(JSONB, nullable=False)
    product_landscape = Column(JSONB)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class MarketDepthReport(Base):
    __tablename__ = "market_depth_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_batch_id = Column(UUID(as_uuid=True), nullable=False)
    gemini_output = Column(JSONB, nullable=False)
    validation_passed = Column(Boolean, nullable=False)
    validation_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketDepthWeights(Base):
    __tablename__ = "market_depth_weights"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    weights = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class MarketDepthJob(Base):
    __tablename__ = "market_depth_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, nullable=False, default="queued")
    error = Column(Text)
    snapshot_batch_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class MarketDepthCompensation(Base):
    __tablename__ = "market_depth_compensation"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_name = Column(String, nullable=False)
    role = Column(String)
    salary_median = Column(Numeric)
    currency = Column(String, default="USD")
    source = Column(String)
    imported_at = Column(DateTime, default=datetime.utcnow)


def run_migrations():
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE market_depth_snapshots "
            "ADD COLUMN IF NOT EXISTS product_landscape JSONB"
        ))
        conn.execute(text(
            "ALTER TABLE market_depth_snapshots "
            "ADD COLUMN IF NOT EXISTS snapshot_batch_id UUID"
        ))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
