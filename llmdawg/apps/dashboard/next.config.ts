import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable React strict mode for surfacing potential issues early
  reactStrictMode: true,

  // Use the src/ directory convention
  // (Next.js auto-detects this; no explicit config needed)

  // Standalone output for Docker — copies only necessary files,
  // resulting in a much smaller production image.
  output: "standalone",

  // Environment variables that are safe to expose to the browser
  // (must also be prefixed NEXT_PUBLIC_ in .env)
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
