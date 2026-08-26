-- 基金组合构建 (Portfolio Construction): 研究型组合——目标配置、候选准入、等权/自定义权重
-- 边界: 组合为研究工具，不执行交易、不做适当性判断、不生成销售规则。

CREATE TYPE "PortfolioStatus" AS ENUM ('draft', 'active', 'archived');
CREATE TYPE "PortfolioWeightSource" AS ENUM ('equal', 'custom');

CREATE TABLE "portfolios" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "name" TEXT NOT NULL,
  "objective" TEXT,
  "status" "PortfolioStatus" NOT NULL DEFAULT 'draft',
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 目标配置: 每行一个同类组的目标权重
CREATE TABLE "portfolio_targets" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "portfolio_id" UUID NOT NULL REFERENCES "portfolios"("id") ON DELETE CASCADE,
  "peer_group_key" TEXT NOT NULL,
  "peer_group_name" TEXT,
  "target_weight" DECIMAL(8, 6) NOT NULL,
  "note" TEXT,
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX "portfolio_targets_portfolio_id_idx" ON "portfolio_targets"("portfolio_id");

-- 组合持仓: 基金 + 权重（等权或自定义）
CREATE TABLE "portfolio_holdings" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "portfolio_id" UUID NOT NULL REFERENCES "portfolios"("id") ON DELETE CASCADE,
  "wind_code" TEXT NOT NULL,
  "weight" DECIMAL(8, 6),
  "weight_source" "PortfolioWeightSource",
  "note" TEXT,
  "added_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT "portfolio_holdings_portfolio_code_key" UNIQUE ("portfolio_id", "wind_code")
);
CREATE INDEX "portfolio_holdings_portfolio_id_idx" ON "portfolio_holdings"("portfolio_id");
CREATE INDEX "portfolio_holdings_wind_code_idx" ON "portfolio_holdings"("wind_code");

-- 组合画像时点快照（M4 建表，M5 回测/监控写入）
CREATE TABLE "portfolio_snapshots" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "portfolio_id" UUID NOT NULL REFERENCES "portfolios"("id") ON DELETE CASCADE,
  "snapshot_date" DATE NOT NULL,
  "holding_count" INTEGER NOT NULL,
  "total_weight" DECIMAL(8, 6) NOT NULL,
  "style_aggregate" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "overlap_matrix" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "correlation_matrix" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "coverage" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX "portfolio_snapshots_portfolio_id_idx" ON "portfolio_snapshots"("portfolio_id");
CREATE INDEX "portfolio_snapshots_snapshot_date_idx" ON "portfolio_snapshots"("snapshot_date");
