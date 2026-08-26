CREATE TABLE IF NOT EXISTS "fund_evaluation_snapshots" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "wind_code" VARCHAR(20) NOT NULL,
  "evaluation_window" VARCHAR(10) NOT NULL,
  "as_of_date" DATE,
  "status" VARCHAR(30) NOT NULL,
  "methodology_version" VARCHAR(100) NOT NULL,
  "calculation_method" VARCHAR(200),
  "peer_group_id" TEXT,
  "peer_group_name" TEXT,
  "overall_score" DECIMAL(5,2),
  "overall_grade" VARCHAR(30),
  "peer_rank" INTEGER,
  "peer_count" INTEGER,
  "peer_percentile" DECIMAL(8,4),
  "dimension_scores" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "peer_metrics" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "data_quality" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "missing_items" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "source_snapshot_ids" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  "snapshot" JSONB NOT NULL,
  "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "fund_evaluation_snapshots_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "fund_evaluation_snapshots_wind_code_fkey"
    FOREIGN KEY ("wind_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "fund_evaluation_snapshots_history_idx"
  ON "fund_evaluation_snapshots"("wind_code", "evaluation_window", "created_at" DESC);
