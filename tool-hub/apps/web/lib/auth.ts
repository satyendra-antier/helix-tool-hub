import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import { findUserByEmail, updateLastLogin, writeAuditLog } from "./hub-db";
import type { HubRole } from "@tool-hub/shared-types";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      orgId: string;
      email: string;
      name: string;
      role: HubRole;
    };
  }
  interface User {
    id: string;
    orgId: string;
    role: HubRole;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    orgId: string;
    role: HubRole;
  }
}

export const authOptions: NextAuthOptions = {
  secret: process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET || "toolhub-dev-secret-change-in-production",
  session: { strategy: "jwt", maxAge: 24 * 60 * 60 },
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        const user = await findUserByEmail(credentials.email);
        if (!user) return null;
        const valid = await bcrypt.compare(credentials.password, user.password_hash);
        if (!valid) return null;
        await updateLastLogin(user.id);
        await writeAuditLog(user.org_id, user.id, "login", { email: user.email });
        return {
          id: user.id,
          orgId: user.org_id,
          email: user.email,
          name: user.name,
          role: user.role,
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id;
        token.orgId = user.orgId;
        token.role = user.role;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id;
        session.user.orgId = token.orgId;
        session.user.role = token.role;
      }
      return session;
    },
  },
};

export function isAdmin(role: HubRole): boolean {
  return role === "admin";
}

export function canOperate(role: HubRole): boolean {
  return role === "admin" || role === "operator";
}
