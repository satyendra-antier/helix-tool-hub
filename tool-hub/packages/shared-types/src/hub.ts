import { z } from "zod";

export const HubRoleSchema = z.enum(["admin", "operator", "viewer"]);
export type HubRole = z.infer<typeof HubRoleSchema>;

export const HubUserSchema = z.object({
  id: z.string().uuid(),
  org_id: z.string().uuid(),
  email: z.string().email(),
  name: z.string(),
  role: HubRoleSchema,
  active: z.boolean(),
  last_login_at: z.string().nullable().optional(),
  created_at: z.string().optional(),
});

export type HubUser = z.infer<typeof HubUserSchema>;

export const AuditLogEntrySchema = z.object({
  id: z.string().uuid(),
  org_id: z.string().uuid(),
  user_id: z.string().uuid().nullable(),
  action: z.string(),
  metadata_jsonb: z.record(z.unknown()).optional(),
  created_at: z.string(),
  user_name: z.string().optional(),
  user_email: z.string().optional(),
});

export type AuditLogEntry = z.infer<typeof AuditLogEntrySchema>;
