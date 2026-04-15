/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow the dashboard to call the gateway during dev without CORS issues
  async rewrites() {
    const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
    return [
      {
        source: "/api/gateway/:path*",
        destination: `${gatewayUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
