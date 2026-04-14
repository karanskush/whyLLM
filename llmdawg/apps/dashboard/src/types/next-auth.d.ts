import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface User {
    accessToken?: string;
    orgId?: string;
    orgName?: string;
    isAdmin?: boolean;
  }

  interface Session {
    accessToken?: string;
    orgId?: string;
    orgName?: string;
    isAdmin?: boolean;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    orgId?: string;
    orgName?: string;
    isAdmin?: boolean;
  }
}
