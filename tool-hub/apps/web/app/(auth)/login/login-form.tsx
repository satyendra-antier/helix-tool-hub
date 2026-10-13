"use client";

import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { BRAND } from "@/lib/journey";
import { Button, Input, Label, Card, CardContent, CardHeader, CardTitle, Alert } from "@tool-hub/ui";

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("admin@toolhub.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    setLoading(false);
    if (res?.error) {
      setError("Invalid email or password");
      return;
    }
    router.push(params.get("callbackUrl") || "/dashboard");
    router.refresh();
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-muted/40 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <Link href="/" className="inline-flex flex-col items-center gap-2">
            <span className="ai-gradient ai-glow flex h-11 w-11 items-center justify-center rounded-xl text-white">
              <Sparkles className="h-5 w-5" />
            </span>
            <p className="text-lg font-semibold ai-text">{BRAND.name}</p>
            <p className="text-sm text-text-secondary">{BRAND.tagline}</p>
          </Link>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              {error ? <Alert variant="danger">{error}</Alert> : null}
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </Button>
            </form>
            <p className="mt-4 text-xs text-text-muted text-center">
              Default admin: admin@toolhub.local — set HUB_ADMIN_PASSWORD in .env
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
