import { Pool, type QueryResultRow } from "pg";
import bcrypt from "bcryptjs";
import type { HubRole, HubUser, AuditLogEntry } from "@tool-hub/shared-types";

let pool: Pool | null = null;

function getPool(): Pool {
  if (!pool) {
    const connectionString =
      process.env.DATABASE_URL || "postgresql://toolhub:toolhub@localhost:5432/toolhub";
    pool = new Pool({ connectionString, max: 10 });
  }
  return pool;
}

const HUB_TABLES_SQL = `
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
`;

let hubReady = false;

export async function ensureHubReady(): Promise<void> {
  if (hubReady) return;
  const db = getPool();
  await db.query(HUB_TABLES_SQL);

  const { rows } = await db.query<{ count: string }>("SELECT COUNT(*)::text AS count FROM hub_users");
  if (parseInt(rows[0]?.count || "0", 10) === 0) {
    const orgResult = await db.query<{ id: string }>(
      `INSERT INTO hub_organizations (name, slug) VALUES ($1, $2) RETURNING id`,
      ["Default Organization", "default"]
    );
    const orgId = orgResult.rows[0].id;
    const password = process.env.HUB_ADMIN_PASSWORD || "admin123";
    const hash = await bcrypt.hash(password, 12);
    await db.query(
      `INSERT INTO hub_users (org_id, email, password_hash, name, role) VALUES ($1, $2, $3, $4, $5)`,
      [orgId, "admin@toolhub.local", hash, "Admin", "admin"]
    );
  }
  hubReady = true;
}

function mapUser(row: QueryResultRow): HubUser {
  return {
    id: row.id,
    org_id: row.org_id,
    email: row.email,
    name: row.name,
    role: row.role as HubRole,
    active: row.active,
    last_login_at: row.last_login_at?.toISOString?.() ?? row.last_login_at ?? null,
    created_at: row.created_at?.toISOString?.() ?? row.created_at,
  };
}

export async function findUserByEmail(email: string): Promise<(HubUser & { password_hash: string }) | null> {
  await ensureHubReady();
  const { rows } = await getPool().query(
    `SELECT * FROM hub_users WHERE email = $1 AND active = true`,
    [email.toLowerCase().trim()]
  );
  if (!rows[0]) return null;
  return { ...mapUser(rows[0]), password_hash: rows[0].password_hash };
}

export async function updateLastLogin(userId: string): Promise<void> {
  await getPool().query(`UPDATE hub_users SET last_login_at = now() WHERE id = $1`, [userId]);
}

export async function listUsers(orgId: string): Promise<HubUser[]> {
  await ensureHubReady();
  const { rows } = await getPool().query(
    `SELECT id, org_id, email, name, role, active, last_login_at, created_at FROM hub_users WHERE org_id = $1 ORDER BY created_at`,
    [orgId]
  );
  return rows.map(mapUser);
}

export async function createUser(
  orgId: string,
  email: string,
  name: string,
  role: HubRole,
  password: string
): Promise<HubUser> {
  await ensureHubReady();
  const hash = await bcrypt.hash(password, 12);
  const { rows } = await getPool().query(
    `INSERT INTO hub_users (org_id, email, password_hash, name, role) VALUES ($1, $2, $3, $4, $5)
     RETURNING id, org_id, email, name, role, active, last_login_at, created_at`,
    [orgId, email.toLowerCase().trim(), hash, name, role]
  );
  return mapUser(rows[0]);
}

export async function updateUserRole(userId: string, role: HubRole): Promise<void> {
  await getPool().query(`UPDATE hub_users SET role = $1 WHERE id = $2`, [role, userId]);
}

export async function deactivateUser(userId: string): Promise<void> {
  await getPool().query(`UPDATE hub_users SET active = false WHERE id = $1`, [userId]);
}

export async function getOrgName(orgId: string): Promise<string> {
  await ensureHubReady();
  const { rows } = await getPool().query(`SELECT name FROM hub_organizations WHERE id = $1`, [orgId]);
  return rows[0]?.name || "Organization";
}

export async function writeAuditLog(
  orgId: string,
  userId: string | null,
  action: string,
  metadata: Record<string, unknown> = {}
): Promise<void> {
  await ensureHubReady();
  await getPool().query(
    `INSERT INTO hub_audit_log (org_id, user_id, action, metadata_jsonb) VALUES ($1, $2, $3, $4)`,
    [orgId, userId, action, JSON.stringify(metadata)]
  );
}

export async function listAuditLog(orgId: string, limit = 100): Promise<AuditLogEntry[]> {
  await ensureHubReady();
  const { rows } = await getPool().query(
    `SELECT a.id, a.org_id, a.user_id, a.action, a.metadata_jsonb, a.created_at,
            u.name AS user_name, u.email AS user_email
     FROM hub_audit_log a
     LEFT JOIN hub_users u ON u.id = a.user_id
     WHERE a.org_id = $1
     ORDER BY a.created_at DESC
     LIMIT $2`,
    [orgId, limit]
  );
  return rows.map((r) => ({
    id: r.id,
    org_id: r.org_id,
    user_id: r.user_id,
    action: r.action,
    metadata_jsonb: r.metadata_jsonb,
    created_at: r.created_at?.toISOString?.() ?? r.created_at,
    user_name: r.user_name,
    user_email: r.user_email,
  }));
}

export async function getHubSetting(orgId: string, key: string): Promise<unknown> {
  await ensureHubReady();
  const { rows } = await getPool().query(
    `SELECT value_jsonb FROM hub_settings WHERE org_id = $1 AND key = $2`,
    [orgId, key]
  );
  return rows[0]?.value_jsonb ?? null;
}

export async function setHubSetting(orgId: string, key: string, value: unknown): Promise<void> {
  await ensureHubReady();
  await getPool().query(
    `INSERT INTO hub_settings (org_id, key, value_jsonb, updated_at) VALUES ($1, $2, $3, now())
     ON CONFLICT (org_id, key) DO UPDATE SET value_jsonb = $3, updated_at = now()`,
    [orgId, key, JSON.stringify(value)]
  );
}

export async function getPipelineConfig(orgId: string, templateId: string): Promise<unknown | null> {
  await ensureHubReady();
  const { rows } = await getPool().query(
    `SELECT config_jsonb FROM hub_pipeline_configs WHERE org_id = $1 AND template_id = $2`,
    [orgId, templateId]
  );
  return rows[0]?.config_jsonb ?? null;
}

export async function savePipelineConfig(orgId: string, templateId: string, config: unknown): Promise<void> {
  await ensureHubReady();
  await getPool().query(
    `INSERT INTO hub_pipeline_configs (org_id, template_id, config_jsonb, updated_at)
     VALUES ($1, $2, $3, now())
     ON CONFLICT (org_id, template_id) DO UPDATE SET config_jsonb = $3, updated_at = now()`,
    [orgId, templateId, JSON.stringify(config)]
  );
}
