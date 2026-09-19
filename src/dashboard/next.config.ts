import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@xfold/protocol"],
  // `dev-isaac` builds into its own directory so it can run next to `dev`.
  distDir: process.env.XFOLD_NEXT_DIST || ".next",
};

export default nextConfig;
