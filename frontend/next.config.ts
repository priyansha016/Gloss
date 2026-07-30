import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Static export: the whole UI is client-rendered against the API, so it ships
  // as plain files to a free static host (Cloudflare Pages). Consequence: no
  // dynamic routes, no server components fetching data — use query params.
  output: "export",
  // /doc → /doc/index.html, so a static host serves it without a rewrite rule.
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
