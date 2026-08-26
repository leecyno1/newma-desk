-- 研究队列 (Research Queue): 候选基金进入"研究中"状态，带优先级、复查日期、产出承诺
CREATE TYPE "ResearchQueueStatus" AS ENUM ('queued', 'researching', 'concluded', 'dropped');

CREATE TABLE "research_queue_items" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "fund_wind_code" TEXT NOT NULL,
  "status" "ResearchQueueStatus" NOT NULL DEFAULT 'queued',
  "priority" INTEGER NOT NULL DEFAULT 3,           -- 1=最高 5=最低
  "source" TEXT,                                    -- 来源：recommendation / watchlist / manual / anomaly
  "source_ref" TEXT,                                -- 来源引用（如候选组名、异常ID）
  "next_review_date" DATE,
  "output_committed" BOOLEAN NOT NULL DEFAULT FALSE, -- 是否已承诺产出（论点/结论）
  "thesis_id" UUID REFERENCES investment_theses(id), -- 关联的投资论点
  "conclusion" TEXT,                                -- 简短结论
  "concluded_at" TIMESTAMPTZ,
  "notes" TEXT,
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "research_queue_status_idx" ON "research_queue_items"("status");
CREATE INDEX "research_queue_fund_idx" ON "research_queue_items"("fund_wind_code");
CREATE INDEX "research_queue_review_idx" ON "research_queue_items"("next_review_date") WHERE "status" IN ('queued','researching');
