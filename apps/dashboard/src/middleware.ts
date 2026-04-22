/**
 * NextAuth middleware — protect /dashboard/* routes.
 * Unauthenticated users are redirected to /login.
 */

export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: ["/dashboard/:path*", "/onboarding"],
};
