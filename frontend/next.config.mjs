/** @type {import('next').NextConfig} */
const nextConfig = {
  // Backend proxy — avoids CORS in dev
  async rewrites() {
    return [
      { source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' },
      { source: '/ws/:path*',  destination: 'http://localhost:8000/ws/:path*'  },
    ];
  },
};

export default nextConfig;
