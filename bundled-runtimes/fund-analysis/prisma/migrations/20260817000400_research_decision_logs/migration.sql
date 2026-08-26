-- 研究决策记录 (Research Decision Logs): 每次研究结论的结构化记录，带证据快照与复查日期
CREATE TABLE "research_decision_logs" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "fund_wind_code" TEXT NOT NULL,
  "thesis_id" UUID REFERENCES investment_theses(id) ON DELETE SET NULL,

  -- 结论类型与内容
  "decision_type" TEXT NOT NULL,            -- 'buy_research' | 'hold' | 'avoid' | 'exit_research' | 'observe'
  "conclusion" TEXT NOT NULL,
  "confidence" TEXT,                        -- 'high' | 'medium' | 'low'

  -- 证据快照 ID（分类/评价/归因/纪要），保证可回放
  "evidence_snapshot" JSONB NOT NULL DEFAULT '{}'::jsonb,

  -- 复查节奏：到期强制回到复盘环节
  "review_after_days" INTEGER NOT NULL DEFAULT 90,
  "review_due_date" DATE,
  "reviewed" BOOLEAN NOT NULL DEFAULT FALSE,
  "review_note" TEXT,

  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "research_decision_logs_fund_idx" ON "research_decision_logs"("fund_wind_code");
CREATE INDEX "research_decision_logs_due_idx" ON "research_decision_logs"("review_due_date") WHERE "reviewed" = FALSE;
CREATE INDEX "research_decision_logs_type_idx" ON "research_decision_logs"("decision_type");
