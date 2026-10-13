import uuid
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, DateTime, Date, Numeric, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class LeadEntity(Base):
    __tablename__ = "leads_entities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    track = Column(String, nullable=False)
    domain = Column(String)
    description = Column(Text)
    source = Column(String, nullable=False)
    signal_type = Column(String)
    signal_value = Column(Numeric)
    signal_date = Column(Date)
    deadline = Column(Date)
    raw_payload = Column(JSONB)
    lead_orientation = Column(String, default="generic")  # demand | future | generic
    matched_domains = Column(JSONB, default=list)
    domain_context = Column(JSONB, default=dict)
    fit_reason = Column(Text)
    sales_check = Column(JSONB)
    sources = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeadContact(Base):
    __tablename__ = "leads_contacts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True))
    full_name = Column(String)
    role_title = Column(String)
    email = Column(String)
    email_verified = Column(Boolean, default=False)
    enrichment_source = Column(String)
    consent_basis = Column(String, nullable=False)
    confidence = Column(Numeric)
    source_url = Column(Text)
    verified_at = Column(DateTime)
    phone = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeadFeedback(Base):
    __tablename__ = "leads_feedback"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True))
    verdict = Column(String, nullable=False)  # good | bad
    breakdown = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeadScore(Base):
    __tablename__ = "leads_scores"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True))
    score = Column(Numeric, nullable=False)
    breakdown = Column(JSONB, nullable=False)
    fit_profile_version = Column(String)
    computed_at = Column(DateTime, default=datetime.utcnow)


class LeadPipeline(Base):
    __tablename__ = "leads_pipeline"
    entity_id = Column(UUID(as_uuid=True), primary_key=True)
    stage = Column(String, nullable=False, default="new")
    outreach_draft = Column(Text)
    outreach_sent_at = Column(DateTime)
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)


class LeadFitProfile(Base):
    __tablename__ = "leads_fit_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keywords = Column(ARRAY(String), nullable=False)
    weights = Column(JSONB, nullable=False)
    version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeadSuppression(Base):
    __tablename__ = "leads_suppression"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeadJob(Base):
    __tablename__ = "leads_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, nullable=False, default="queued")
    error = Column(Text)
    entities_found = Column(Numeric, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS leads_entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  track TEXT NOT NULL,
  domain TEXT,
  description TEXT,
  source TEXT NOT NULL,
  signal_type TEXT,
  signal_value NUMERIC,
  signal_date DATE,
  deadline DATE,
  raw_payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID REFERENCES leads_entities(id),
  full_name TEXT,
  role_title TEXT,
  email TEXT,
  email_verified BOOLEAN DEFAULT false,
  enrichment_source TEXT,
  consent_basis TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID REFERENCES leads_entities(id),
  score NUMERIC NOT NULL,
  breakdown JSONB NOT NULL,
  fit_profile_version TEXT,
  computed_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_pipeline (
  entity_id UUID PRIMARY KEY REFERENCES leads_entities(id),
  stage TEXT NOT NULL DEFAULT 'new',
  outreach_draft TEXT,
  outreach_sent_at TIMESTAMPTZ,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_fit_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  keywords TEXT[] NOT NULL,
  weights JSONB NOT NULL,
  version TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_suppression (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  reason TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  entities_found NUMERIC DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);
"""


def run_migrations():
    with engine.connect() as conn:
        for stmt in MIGRATION_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
        conn.execute(text(
            "ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS lead_orientation TEXT DEFAULT 'generic'"
        ))
        conn.execute(text(
            "ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS matched_domains JSONB DEFAULT '[]'"
        ))
        conn.execute(text(
            "ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS domain_context JSONB DEFAULT '{}'"
        ))
        for col, typ in (
            ("confidence", "NUMERIC"), ("source_url", "TEXT"),
            ("verified_at", "TIMESTAMPTZ"), ("phone", "TEXT"),
        ):
            conn.execute(text(f"ALTER TABLE leads_contacts ADD COLUMN IF NOT EXISTS {col} {typ}"))
        conn.execute(text("ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS fit_reason TEXT"))
        conn.execute(text("ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS sales_check JSONB"))
        conn.execute(text("ALTER TABLE leads_entities ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS leads_feedback (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              entity_id UUID REFERENCES leads_entities(id) ON DELETE CASCADE,
              verdict TEXT NOT NULL,
              breakdown JSONB,
              created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
