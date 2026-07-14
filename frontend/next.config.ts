import type { NextConfig } from "next";

let nextPublicApiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
if (nextPublicApiUrl && !nextPublicApiUrl.startsWith("http://") && !nextPublicApiUrl.startsWith("https://") && !nextPublicApiUrl.startsWith("/")) {
  nextPublicApiUrl = `https://${nextPublicApiUrl}`;
}

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ${nextPublicApiUrl}; frame-ancestors 'none'; base-uri 'self'; form-action 'self';`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
