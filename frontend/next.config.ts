import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Disable compression so SSE streams are not buffered or gzipped in chunked responses over tunnels
  compress: false,
  // The browser only ever talks to the frontend origin. API calls are proxied to the backend,
  // so a single public tunnel serves the whole app and auth cookies stay same-origin.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${backendUrl}/api/v1/:path*` }];
  },
  // Lets the dev server accept requests that arrive through an ngrok tunnel.
  allowedDevOrigins: ["*.ngrok-free.app", "*.ngrok-free.dev", "*.ngrok.app", "*.ngrok.dev", "*.ngrok.io"],
};

export default nextConfig;
