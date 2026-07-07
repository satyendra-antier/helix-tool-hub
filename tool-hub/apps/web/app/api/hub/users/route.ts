import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { listUsers, createUser, updateUserRole, deactivateUser, writeAuditLog } from "@/lib/hub-db";
import type { HubRole } from "@tool-hub/shared-types";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user || session.user.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const users = await listUsers(session.user.orgId);
  return NextResponse.json({ users });
}

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user || session.user.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const body = await req.json();
  const { email, name, role, password } = body;
  if (!email || !name || !password) {
    return NextResponse.json({ error: "email, name, password required" }, { status: 400 });
  }
  const user = await createUser(
    session.user.orgId,
    email,
    name,
    (role as HubRole) || "viewer",
    password
  );
  await writeAuditLog(session.user.orgId, session.user.id, "user.create", { email, role });
  return NextResponse.json({ user });
}

export async function PATCH(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user || session.user.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const body = await req.json();
  const { userId, role, active } = body;
  if (!userId) {
    return NextResponse.json({ error: "userId required" }, { status: 400 });
  }
  if (role) {
    await updateUserRole(userId, role as HubRole);
    await writeAuditLog(session.user.orgId, session.user.id, "user.role.update", { userId, role });
  }
  if (active === false) {
    await deactivateUser(userId);
    await writeAuditLog(session.user.orgId, session.user.id, "user.deactivate", { userId });
  }
  return NextResponse.json({ ok: true });
}
