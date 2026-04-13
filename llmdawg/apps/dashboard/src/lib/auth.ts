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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.accessToken = (user as any).accessToken;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.orgId = (user as any).orgId;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.orgName = (user as any).orgName;
      }
      return token;
    },
    async session({ session, token }) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).accessToken = token.accessToken;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).orgId = token.orgId;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).orgName = token.orgName;
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  session: { strategy: "jwt" },
});
