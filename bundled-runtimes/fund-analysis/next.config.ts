import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  output: 'standalone', // 支持 Docker 部署
};

export default nextConfig;
