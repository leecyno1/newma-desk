-- 决策复盘 (Decision Post-mortems): 投资论点关闭后强制复盘
CREATE TABLE "decision_postmortems" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "thesis_id" UUID NOT NULL REFERENCES investment_theses(id) ON DELETE CASCADE,
  "fund_wind_code" TEXT NOT NULL,

  -- 论点关闭时的结果
  "outcome" TEXT NOT NULL,                     -- 'validated' | 'invalidated' | 'inconclusive'
  "actual_return_pct" DOUBLE PRECISION,        -- 实际收益（论点期间）
  "peer_median_return_pct" DOUBLE PRECISION,   -- 同类中位收益
  "excess_return_pct" DOUBLE PRECISION,        -- 超额收益

  -- 核心逻辑验证：哪些 core_reasoning 被证实/证伪
  "reasoning_verdicts" JSONB NOT NULL DEFAULT '[]'::jsonb,

  -- 卖出触发是否被触发
  "trigger_fired" BOOLEAN NOT NULL DEFAULT FALSE,
  "trigger_detail" TEXT,

  -- 反思与教训
  "lesson_learned" TEXT,
  "decision_bias" TEXT,                        -- 识别出的决策偏差类型
  "would_repeat" BOOLEAN,                      -- 是否会重复同样决策

  "reviewed_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "decision_postmortems_thesis_idx" ON "decision_postmortems"("thesis_id");
CREATE INDEX "decision_postmortems_fund_idx" ON "decision_postmortems"("fund_wind_code");
CREATE INDEX "decision_postmortems_outcome_idx" ON "decision_postmortems"("outcome");
