import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api/* is proxied to FastAPI, so there is no
// CORS to configure and the API URL never ships to the client. In Docker, API_URL is the
// compose service name, baked in at build time.
const apiUrl = process.env.API_URL ?? "http://localhost:8000";
const dev = process.env.NODE_ENV !== "production";

// Everything is served from this origin: no CDN, no external fonts, no third-party scripts.
// 'unsafe-inline' scripts are what Next's App Router hydration needs without nonces (which
// would make every page dynamic); the rest still blocks loading code or frames from
// elsewhere. Dev adds eval and the HMR websocket.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${dev ? " ws:" : ""}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The rewrite proxy's default 30 s timeout would cut long streamed chat answers short.
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/health", destination: `${apiUrl}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default config;
