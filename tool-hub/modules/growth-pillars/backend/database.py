import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, Integer, String, Text, Uuid, create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

_engine_kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _id():
    return Column(Uuid, primary_key=True, default=uuid.uuid4)


class Expert(Base):
    __tablename__ = "pillars_experts"
    id = _id()
    full_name = Column(String, nullable=False)
    title = Column(String)
    organization = Column(String)
    email = Column(String)
    linkedin_url = Column(String)
    domains = Column(JSON, default=list)
    companies = Column(JSON, default=list)
    relationship_strength = Column(Integer, default=3)  # 1 (weak) .. 5 (close)
    notes = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class IntroRequest(Base):
    __tablename__ = "pillars_intros"
    id = _id()
    lead_id = Column(String, nullable=False, index=True)
    lead_name = Column(String)
    expert_id = Column(Uuid, nullable=False, index=True)
    match_score = Column(Float, default=0)
    rationale = Column(Text)
    subject = Column(String)
    body = Column(Text)
    # draft -> approved -> requested -> introduced | declined
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class WatchedAccount(Base):
    __tablename__ = "pillars_watchlist"
    id = _id()
    lead_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    domain = Column(String)
    track = Column(String)
    baseline = Column(JSON, default=dict)
    active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class InsiderAlert(Base):
    __tablename__ = "pillars_alerts"
    id = _id()
    account_id = Column(Uuid, index=True)
    lead_id = Column(String, index=True)
    account_name = Column(String)
    alert_type = Column(String)  # score_jump | new_signal | deadline | news | hiring
    severity = Column(String, default="medium")  # low | medium | high
    title = Column(String, nullable=False)
    detail = Column(Text)
    url = Column(String)
    fingerprint = Column(String, unique=True, index=True)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChannelPartner(Base):
    __tablename__ = "pillars_partners"
    id = _id()
    name = Column(String, nullable=False)
    website = Column(String)
    partner_type = Column(String)  # agency | consultancy | integrator | vc_platform | other
    services = Column(JSON, default=list)
    domains = Column(JSON, default=list)
    fit_score = Column(Float, default=0)
    fit_reasons = Column(JSON, default=list)
    verified = Column(Boolean, default=False)
    source = Column(String, default="manual")  # manual | ai_suggested
    # prospect -> talking -> signed | dropped
    stage = Column(String, default="prospect")
    contact_name = Column(String)
    contact_email = Column(String)
    notes = Column(Text)
    referrals_received = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class VisibilityQuery(Base):
    __tablename__ = "pillars_visibility_queries"
    id = _id()
    query = Column(String, nullable=False)
    domain = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VisibilityCheck(Base):
    __tablename__ = "pillars_visibility_checks"
    id = _id()
    query_id = Column(Uuid, index=True)
    query = Column(String)
    provider = Column(String)  # openai | perplexity
    model = Column(String)
    mentioned = Column(Boolean, default=False)
    rank = Column(Integer)
    competitors = Column(JSON, default=list)
    citations = Column(JSON, default=list)
    answer_excerpt = Column(Text)
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)


class SalesAdvice(Base):
    __tablename__ = "pillars_advice"
    id = _id()
    lead_id = Column(String, index=True)
    lead_name = Column(String)
    next_best_action = Column(Text)
    recommended_path = Column(String)  # direct | expert_intro | partner | nurture
    talking_points = Column(JSON, default=list)
    objections = Column(JSON, default=list)
    deal_risk = Column(String)  # low | medium | high
    risk_reasons = Column(JSON, default=list)
    inputs = Column(JSON, default=dict)
    generated_by = Column(String)  # llm | heuristic
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DealDoc(Base):
    """Deal Coach output for one lead: meeting_prep | playbook | proposal | handoff."""
    __tablename__ = "pillars_deal_docs"
    id = _id()
    lead_id = Column(String, index=True, nullable=False)
    lead_name = Column(String)
    kind = Column(String, nullable=False, index=True)
    content = Column(JSON, default=dict)
    generated_by = Column(String)  # llm | template
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SignalRecipe(Base):
    """Saved rule like 'raised funding' or 'hiring a CTO' that sends matching leads to Reach Out."""
    __tablename__ = "pillars_recipes"
    id = _id()
    name = Column(String, nullable=False)
    description = Column(Text)
    signal_types = Column(JSON, default=list)
    alert_types = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    min_score = Column(Float, default=50)
    auto_enroll = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    matched_total = Column(Integer, default=0)
    enrolled_total = Column(Integer, default=0)
    last_run_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecipeMatch(Base):
    __tablename__ = "pillars_recipe_matches"
    id = _id()
    recipe_id = Column(Uuid, index=True, nullable=False)
    lead_id = Column(String, index=True, nullable=False)
    lead_name = Column(String)
    reason = Column(Text)
    enrolled = Column(Boolean, default=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PillarJob(Base):
    __tablename__ = "pillars_jobs"
    id = _id()
    job_type = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued | running | done | failed
    progress = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


def run_migrations() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
