import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { getPipelineConfig, savePipelineConfig, writeAuditLog } from "@/lib/hub-db";
import { DEFAULT_PIPELINE_CONFIG, PipelineConfigSchema } from "@tool-hub/shared-types";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const stored = await getPipelineConfig(session.user.orgId, "revenue-flywheel");
  const config = stored || DEFAULT_PIPELINE_CONFIG;
  return NextResponse.json({ config });
}

export async function PUT(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (session.user.role === "viewer") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const body = await req.json();
  const parsed = PipelineConfigSchema.safeParse(body.config || body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid config", details: parsed.error.flatten() }, { status: 400 });
  }
  const config = { ...parsed.data, updatedAt: new Date().toISOString() };
  await savePipelineConfig(session.user.orgId, "revenue-flywheel", config);
  await writeAuditLog(session.user.orgId, session.user.id, "pipeline.config.save", { templateId: config.templateId });
  return NextResponse.json({ config });
}
