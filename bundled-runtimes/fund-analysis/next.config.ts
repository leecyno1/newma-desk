import type { NextConfig } from "next";
import { readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';

// Optional local sharing: read only the server database setting, never model keys.
// Explicit DATABASE_URL always takes precedence; nothing is exposed via Next's env config.
const databaseEnvFile = process.env.NEWMA_DESK_FUND_DATABASE_ENV_FILE;
if (!process.env.DATABASE_URL && databaseEnvFile) {
  const databaseUrl = parseEnv(readFileSync(databaseEnvFile, 'utf8')).DATABASE_URL;
  if (!databaseUrl) throw new Error('基金数据库配置文件缺少 DATABASE_URL');
  process.env.DATABASE_URL = databaseUrl;
}

const nextConfig: NextConfig = {
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  output: 'standalone', // 支持 Docker 部署
};

export default nextConfig;
