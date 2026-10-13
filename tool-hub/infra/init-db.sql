CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Video Scraper tables
CREATE TABLE IF NOT EXISTS video_scraper_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url TEXT NOT NULL,
  source_type TEXT,
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
  completed_at TIMESTAMPTZ,
  is_batch BOOLEAN DEFAULT false,
  progress_json JSONB
);

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

-- Market Depth tables
CREATE TABLE IF NOT EXISTS market_depth_domains (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  track TEXT NOT NULL,
  keywords TEXT[] NOT NULL,
  active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS market_depth_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id UUID REFERENCES market_depth_domains(id),
  snapshot_batch_id UUID,
  raw_evidence JSONB NOT NULL,
  component_scores JSONB NOT NULL,
  composite_score NUMERIC NOT NULL,
  weights_used JSONB NOT NULL,
  product_landscape JSONB,
  fetched_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_depth_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_batch_id UUID NOT NULL,
  gemini_output JSONB NOT NULL,
  validation_passed BOOLEAN NOT NULL,
  validation_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_depth_weights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  weights JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_depth_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  snapshot_batch_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS market_depth_compensation (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_name TEXT NOT NULL,
  role TEXT,
  salary_median NUMERIC,
  currency TEXT DEFAULT 'USD',
  source TEXT,
  imported_at TIMESTAMPTZ DEFAULT now()
);

-- Lead Intelligence tables
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

-- Build Readiness Engine tables
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
);

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
);

CREATE TABLE IF NOT EXISTS build_readiness_capabilities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  evidence_count INT DEFAULT 1,
  sample_urls TEXT[] DEFAULT '{}',
  depth_score NUMERIC DEFAULT 0,
  extracted_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS build_readiness_verdicts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL,
  analysis_batch_id UUID,
  domain_id UUID,
  domain_name TEXT NOT NULL,
  track TEXT NOT NULL,
  market_score NUMERIC NOT NULL,
  capability_score NUMERIC NOT NULL,
  opportunity_score NUMERIC NOT NULL,
  verdict TEXT NOT NULL,
  verdict_json JSONB NOT NULL,
  citations JSONB DEFAULT '[]',
  market_fetched_at TIMESTAMPTZ,
  company_indexed_at TIMESTAMPTZ,
  analyzed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS build_readiness_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  progress JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS build_readiness_index_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL,
  job_id UUID,
  source_type TEXT NOT NULL,
  pages_indexed INT DEFAULT 0,
  chunks_indexed INT DEFAULT 0,
  capabilities_found INT DEFAULT 0,
  indexed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS build_readiness_analysis_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL,
  job_id UUID,
  market_fetched_at TIMESTAMPTZ,
  company_indexed_at TIMESTAMPTZ,
  domains_analyzed INT DEFAULT 0,
  go_count INT DEFAULT 0,
  analyzed_at TIMESTAMPTZ DEFAULT now()
);

-- Hub platform tables (auth, settings, pipeline, audit)
CREATE TABLE IF NOT EXISTS hub_organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hub_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES hub_organizations(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'operator', 'viewer')),
  active BOOLEAN DEFAULT true,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hub_users_org ON hub_users(org_id);

CREATE TABLE IF NOT EXISTS hub_settings (
  org_id UUID NOT NULL REFERENCES hub_organizations(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_jsonb JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, key)
);

CREATE TABLE IF NOT EXISTS hub_pipeline_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES hub_organizations(id) ON DELETE CASCADE,
  template_id TEXT NOT NULL,
  config_jsonb JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (org_id, template_id)
);

CREATE TABLE IF NOT EXISTS hub_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES hub_organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES hub_users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  metadata_jsonb JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hub_audit_org ON hub_audit_log(org_id, created_at DESC);

-- Reach Out (outreach-autopilot)
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
);
