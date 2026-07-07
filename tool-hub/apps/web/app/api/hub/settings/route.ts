import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { getHubSetting, setHubSetting, writeAuditLog } from "@/lib/hub-db";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const settings = await getHubSetting(session.user.orgId, "platform");
  return NextResponse.json({ settings: settings || {} });
}

export async function PATCH(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user || session.user.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const body = await req.json();
  await setHubSetting(session.user.orgId, "platform", body);
  await writeAuditLog(session.user.orgId, session.user.id, "settings.update", { keys: Object.keys(body) });
  return NextResponse.json({ ok: true });
}
