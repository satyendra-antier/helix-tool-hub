import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _uuid():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class OutreachSetting(Base):
    __tablename__ = "outreach_settings"
    key = Column(String, primary_key=True)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Mailbox(Base):
    __tablename__ = "outreach_mailboxes"
    id = _uuid()
    label = Column(String, nullable=False)
    email = Column(String, nullable=False)
    from_name = Column(String)
    kind = Column(String, nullable=False, default="smtp")  # smtp | sandbox
    smtp_host = Column(String)
    smtp_port = Column(Integer, default=587)
    smtp_security = Column(String, default="starttls")  # starttls | ssl | none
    imap_host = Column(String)
    imap_port = Column(Integer, default=993)
    username = Column(String)
    secret_enc = Column(Text)
    daily_cap_start = Column(Integer, default=20)
    daily_cap_max = Column(Integer, default=50)
    ramp_per_day = Column(Integer, default=5)
    active = Column(Boolean, default=True)
    paused_reason = Column(Text)
    sent_today = Column(Integer, default=0)
    sent_today_date = Column(String)
    sent_total = Column(Integer, default=0)
    bounced_total = Column(Integer, default=0)
    last_seen_uid = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Sequence(Base):
    __tablename__ = "outreach_sequences"
    id = _uuid()
    name = Column(String, nullable=False)
    steps = Column(JSONB, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Enrollment(Base):
    __tablename__ = "outreach_enrollments"
    id = _uuid()
    lead_id = Column(String, nullable=False)
    lead_name = Column(String)
    company_domain = Column(String)
    contact_email = Column(String, nullable=False)
    contact_name = Column(String)
    contact_title = Column(String)
    phone = Column(String)
    mailbox_id = Column(UUID(as_uuid=True))
    sequence_id = Column(UUID(as_uuid=True))
    current_step = Column(Integer, default=0)
    status = Column(String, nullable=False, default="awaiting_approval")
    next_action_at = Column(DateTime)
    thread_message_id = Column(String)
    subject = Column(String)
    last_sent_at = Column(DateTime)
    lead_score = Column(Numeric)
    fit_reason = Column(Text)
    context = Column(JSONB, default=dict)
    call_status = Column(String)
    crm_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "outreach_messages"
    id = _uuid()
    enrollment_id = Column(UUID(as_uuid=True), nullable=False)
    step = Column(Integer, nullable=False, default=1)
    kind = Column(String)  # opener | follow_up | insight | soft_close | answer
    status = Column(String, nullable=False, default="draft")  # draft | approved | sent | failed | rejected
    subject = Column(String)
    body = Column(Text)
    message_id = Column(String)
    in_reply_to = Column(String)
    sent_at = Column(DateTime)
    error = Column(Text)
    needs_approval = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reply(Base):
    __tablename__ = "outreach_replies"
    id = _uuid()
    enrollment_id = Column(UUID(as_uuid=True))
    mailbox_id = Column(UUID(as_uuid=True))
    message_id = Column(String)
    from_email = Column(String)
    subject = Column(String)
    body = Column(Text)
    category = Column(String)
    confidence = Column(Numeric)
    reasoning = Column(Text)
    action_taken = Column(Text)
    handled = Column(Boolean, default=False)
    received_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "outreach_events"
    id = _uuid()
    enrollment_id = Column(UUID(as_uuid=True))
    kind = Column(String, nullable=False)
    detail = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Call(Base):
    __tablename__ = "outreach_calls"
    id = _uuid()
    enrollment_id = Column(UUID(as_uuid=True), nullable=False)
    phone = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")  # queued | dialing | completed | failed | skipped
    outcome = Column(String)  # interested | call_back | not_interested | wrong_number | no_answer
    provider_call_id = Column(String)
    summary = Column(Text)
    transcript = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class Job(Base):
    __tablename__ = "outreach_jobs"
    id = _uuid()
    kind = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    result = Column(JSONB)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS outreach_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS outreach_mailboxes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label TEXT NOT NULL,
  email TEXT NOT NULL,
  from_name TEXT,
  kind TEXT NOT NULL DEFAULT 'smtp',
  smtp_host TEXT,
  smtp_port INT DEFAULT 587,
  smtp_security TEXT DEFAULT 'starttls',
  imap_host TEXT,
  imap_port INT DEFAULT 993,
  username TEXT,
  secret_enc TEXT,
  daily_cap_start INT DEFAULT 20,
  daily_cap_max INT DEFAULT 50,
  ramp_per_day INT DEFAULT 5,
  active BOOLEAN DEFAULT true,
  paused_reason TEXT,
  sent_today INT DEFAULT 0,
  sent_today_date TEXT,
  sent_total INT DEFAULT 0,
  bounced_total INT DEFAULT 0,
  last_seen_uid INT DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS outreach_sequences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  steps JSONB NOT NULL,
  is_default BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS outreach_enrollments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id TEXT NOT NULL,
  lead_name TEXT,
  company_domain TEXT,
  contact_email TEXT NOT NULL,
  contact_name TEXT,
  contact_title TEXT,
  phone TEXT,
  mailbox_id UUID,
  sequence_id UUID,
  current_step INT DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'awaiting_approval',
  next_action_at TIMESTAMP,
  thread_message_id TEXT,
  subject TEXT,
  last_sent_at TIMESTAMP,
  lead_score NUMERIC,
  fit_reason TEXT,
  context JSONB DEFAULT '{}',
  call_status TEXT,
  crm_synced_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE UNIQUE INDEX IF NOT EXISTS outreach_enrollments_lead_email ON outreach_enrollments (lead_id, contact_email);
CREATE INDEX IF NOT EXISTS outreach_enrollments_status ON outreach_enrollments (status, next_action_at);
CREATE TABLE IF NOT EXISTS outreach_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID NOT NULL REFERENCES outreach_enrollments(id) ON DELETE CASCADE,
  step INT NOT NULL DEFAULT 1,
  kind TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  subject TEXT,
  body TEXT,
  message_id TEXT,
  in_reply_to TEXT,
  sent_at TIMESTAMP,
  error TEXT,
  needs_approval BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS outreach_messages_message_id ON outreach_messages (message_id);
CREATE TABLE IF NOT EXISTS outreach_replies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID REFERENCES outreach_enrollments(id) ON DELETE CASCADE,
  mailbox_id UUID,
  message_id TEXT,
  from_email TEXT,
  subject TEXT,
  body TEXT,
  category TEXT,
  confidence NUMERIC,
  reasoning TEXT,
  action_taken TEXT,
  handled BOOLEAN DEFAULT false,
  received_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE UNIQUE INDEX IF NOT EXISTS outreach_replies_message_id ON outreach_replies (message_id);
CREATE TABLE IF NOT EXISTS outreach_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID,
  kind TEXT NOT NULL,
  detail JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS outreach_events_created ON outreach_events (created_at DESC);
CREATE TABLE IF NOT EXISTS outreach_calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID NOT NULL REFERENCES outreach_enrollments(id) ON DELETE CASCADE,
  phone TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  outcome TEXT,
  provider_call_id TEXT,
  summary TEXT,
  transcript TEXT,
  error TEXT,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
  completed_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS outreach_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  result JSONB,
  error TEXT,
  created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
  completed_at TIMESTAMP
)
"""


def run_migrations() -> None:
    with engine.connect() as conn:
        for stmt in MIGRATION_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
