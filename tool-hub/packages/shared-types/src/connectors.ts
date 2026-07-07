import { z } from "zod";

export const ConnectorTypeSchema = z.enum(["api_key", "oauth", "public"]);
export type ConnectorType = z.infer<typeof ConnectorTypeSchema>;

export const ConnectorDefinitionSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: ConnectorTypeSchema,
  description: z.string(),
  usedByModules: z.array(z.string()),
  envKeys: z.array(z.string()).optional(),
});

export type ConnectorDefinition = z.infer<typeof ConnectorDefinitionSchema>;
