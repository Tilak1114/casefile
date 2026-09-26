import type { NextConfig } from "next";

// Static export: the deployed UI reads only the exported run bundle, so it needs no server or database.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
