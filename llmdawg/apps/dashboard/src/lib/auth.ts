/**
 * NextAuth v5 (beta.25) configuration.
 *
 * Strategy: Credentials provider → POST /api/v1/auth/login → store JWT in
 * NextAuth session token so it can be forwarded to the backend on each request.
 */

import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import { auth as apiAuth } from "@/lib/api";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        // Demo admin account — no backend required
        if (
          credentials.email === "admin" &&
          credentials.password === "admin"
        ) {
          return {
            id: "admin-001",
            email: "admin@whyllm.dev",
            name: "Admin",
            accessToken: "demo-token",
            orgId: "org-demo",
            orgName: "Demo Org",
            isAdmin: true,
          };
        }

        try {
          const res = await apiAuth.login({
            email: credentials.email as string,
            password: credentials.password as string,
          });
          if (!res.access_token) return null;
          return {
            id: res.user.id,
            email: res.user.email,
            name: res.user.name ?? undefined,
            accessToken: res.access_token,
            orgId: res.user.org_id ?? undefined,
            orgName: res.user.org_name ?? undefined,
            isAdmin: res.user.is_admin ?? false,
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = user.accessToken;
        token.orgId = user.orgId;
        token.orgName = user.orgName;
        token.isAdmin = user.isAdmin;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.orgId = token.orgId;
      session.orgName = token.orgName;
      session.isAdmin = token.isAdmin;
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  session: { strategy: "jwt" },
});
