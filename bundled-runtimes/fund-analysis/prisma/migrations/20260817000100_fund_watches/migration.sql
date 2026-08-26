-- 观察项 (Fund Watches): 用户可对任意基金+任意指标设置阈值观察
CREATE TYPE "WatchStatus" AS ENUM ('active', 'triggered', 'dismissed');

CREATE TABLE "fund_watches" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "fund_wind_code" TEXT NOT NULL,
  "metric_field" TEXT NOT NULL,       -- e.g. total_asset, max_drawdown_1y, top_ten_weight
  "operator" TEXT NOT NULL DEFAULT '>=', -- >, <, >=, <=
  "threshold" DOUBLE PRECISION NOT NULL,
  "note" TEXT,
  "status" "WatchStatus" NOT NULL DEFAULT 'active',
  "triggered_at" TIMESTAMPTZ,
  "triggered_value" DOUBLE PRECISION,
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "fund_watches_fund_idx" ON "fund_watches"("fund_wind_code");
CREATE INDEX "fund_watches_status_idx" ON "fund_watches"("status");
