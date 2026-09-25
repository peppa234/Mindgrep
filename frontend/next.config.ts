import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api/* is proxied to FastAPI, so there is no
// CORS to configure and the API URL never ships to the client. In Docker, API_URL is the
// compose service name, baked in at build time.
const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/health", destination: `${apiUrl}/health` },
    ];
  },
};

export default config;
