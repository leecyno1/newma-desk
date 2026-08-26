-- CreateEnum for investment thesis lifecycle state
CREATE TYPE "InvestmentThesisState" AS ENUM (
  'candidate',      -- 候选中：刚建立论点，尚未深度研究
  'researching',    -- 研究中：正在深入研究、补齐证据
  'observing',      -- 建立观察：论点已成型，进入跟踪期
  'invalid',        -- 论点失效：卖出触发被触发或核心逻辑被证伪
  'archived'        -- 已归档：手动关闭
);

CREATE TABLE "investment_theses" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "fund_wind_code" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "state" "InvestmentThesisState" NOT NULL DEFAULT 'candidate',

  -- 核心逻辑：3-5 条为什么买
  "core_reasoning" JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- 卖出触发条件：结构化（价格/规模/经理/风格/归因残差）
  "sell_triggers" JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- 一句话摘要（快速识别用）
  "one_liner" TEXT,
  -- 反向观点（可选，用于对冲确认偏差）
  "counter_view" TEXT,
  -- 主要风险
  "risks" JSONB NOT NULL DEFAULT '[]'::jsonb,

  -- 论点有效期与复查节奏
  "valid_until" DATE,
  "next_review_date" DATE,
  "review_cadence_days" INTEGER NOT NULL DEFAULT 30,

  -- 支撑证据的快照 ID（分类、评价、归因、纪要）
  "evidence_snapshot" JSONB NOT NULL DEFAULT '{}'::jsonb,

  -- 状态机历史（每次 state transition 追加）
  "state_history" JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- 论点编辑历史（每次核心字段变更追加）
  "edit_history" JSONB NOT NULL DEFAULT '[]'::jsonb,

  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "closed_at" TIMESTAMPTZ,

  -- 论点关闭时的结果记录（用于日后复盘）
  "close_reason" TEXT,
  "close_verdict" TEXT
);

CREATE INDEX "investment_theses_fund_wind_code_idx" ON "investment_theses"("fund_wind_code");
CREATE INDEX "investment_theses_state_idx" ON "investment_theses"("state");
CREATE INDEX "investment_theses_next_review_idx" ON "investment_theses"("next_review_date") WHERE "state" IN ('candidate', 'researching', 'observing');
