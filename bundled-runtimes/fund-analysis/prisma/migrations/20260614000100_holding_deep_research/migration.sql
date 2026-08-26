-- Holding look-through and similarity foundation for fund research.

CREATE TABLE "holding_lookthrough_snapshots" (
    "id" TEXT NOT NULL,
    "fund_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "top_ten_weight" DECIMAL(8,4),
    "top_three_weight" DECIMAL(8,4),
    "top_industry" TEXT,
    "top_industry_weight" DECIMAL(8,4),
    "industry_buckets" JSONB,
    "theme_tags" TEXT[],
    "style_tags" TEXT[],
    "market_cap_buckets" JSONB,
    "turnover_estimate" DECIMAL(8,4),
    "heavy_position_changes" JSONB,
    "evidence_refs" JSONB,
    "quality_status" TEXT NOT NULL DEFAULT 'draft',
    "source" TEXT NOT NULL DEFAULT 'holding_lookthrough_tool',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "holding_lookthrough_snapshots_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "holding_similarities" (
    "id" TEXT NOT NULL,
    "fund_a_id" TEXT NOT NULL,
    "fund_b_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "overlap_weight" DECIMAL(8,4),
    "jaccard_score" DECIMAL(8,4),
    "common_holdings" JSONB,
    "similarity_level" TEXT NOT NULL DEFAULT 'unknown',
    "evidence_refs" JSONB,
    "source" TEXT NOT NULL DEFAULT 'holding_similarity_tool',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "holding_similarities_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "holding_lookthrough_snapshots_fund_id_quarter_key"
  ON "holding_lookthrough_snapshots"("fund_id", "quarter");
CREATE INDEX "holding_lookthrough_snapshots_fund_id_quarter_idx"
  ON "holding_lookthrough_snapshots"("fund_id", "quarter");
CREATE INDEX "holding_lookthrough_snapshots_top_industry_idx"
  ON "holding_lookthrough_snapshots"("top_industry");
CREATE INDEX "holding_lookthrough_snapshots_quality_status_idx"
  ON "holding_lookthrough_snapshots"("quality_status");

CREATE UNIQUE INDEX "holding_similarities_fund_a_id_fund_b_id_quarter_key"
  ON "holding_similarities"("fund_a_id", "fund_b_id", "quarter");
CREATE INDEX "holding_similarities_fund_a_id_quarter_idx"
  ON "holding_similarities"("fund_a_id", "quarter");
CREATE INDEX "holding_similarities_fund_b_id_quarter_idx"
  ON "holding_similarities"("fund_b_id", "quarter");
CREATE INDEX "holding_similarities_similarity_level_idx"
  ON "holding_similarities"("similarity_level");

ALTER TABLE "holding_lookthrough_snapshots"
  ADD CONSTRAINT "holding_lookthrough_snapshots_fund_id_fkey"
  FOREIGN KEY ("fund_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "holding_similarities"
  ADD CONSTRAINT "holding_similarities_fund_a_id_fkey"
  FOREIGN KEY ("fund_a_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "holding_similarities"
  ADD CONSTRAINT "holding_similarities_fund_b_id_fkey"
  FOREIGN KEY ("fund_b_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;
