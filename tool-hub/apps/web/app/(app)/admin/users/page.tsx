"use client";

import { useEffect, useState } from "react";
import type { HubUser, HubRole } from "@tool-hub/shared-types";
import {
  PageHeader,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Badge,
} from "@tool-hub/ui";

function SelectNative({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      className="flex h-9 w-full rounded-md border border-border bg-surface px-3 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {children}
    </select>
  );
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<HubUser[]>([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<HubRole>("viewer");

  async function load() {
    const res = await fetch("/api/hub/users");
    if (res.ok) {
      const data = await res.json();
      setUsers(data.users);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createUser() {
    await fetch("/api/hub/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, password, role }),
    });
    setEmail("");
    setName("");
    setPassword("");
    load();
  }

  async function changeRole(userId: string, newRole: HubRole) {
    await fetch("/api/hub/users", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId, role: newRole }),
    });
    load();
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Users & Roles" description="Manage platform access — admin, operator, viewer." />
      <Card>
        <CardContent className="pt-6 space-y-3">
          <p className="text-sm font-medium">Invite user</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><Label>Email</Label><Input value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            <div><Label>Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><Label>Password</Label><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
            <div>
              <Label>Role</Label>
              <SelectNative value={role} onChange={(v) => setRole(v as HubRole)}>
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </SelectNative>
            </div>
          </div>
          <Button onClick={createUser}>Create user</Button>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6 divide-y divide-border">
          {users.map((u) => (
            <div key={u.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0">
              <div>
                <p className="font-medium text-sm">{u.name}</p>
                <p className="text-xs text-text-muted">{u.email}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{u.role}</Badge>
                <SelectNative value={u.role} onChange={(v) => changeRole(u.id, v as HubRole)}>
                  <option value="admin">Admin</option>
                  <option value="operator">Operator</option>
                  <option value="viewer">Viewer</option>
                </SelectNative>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
