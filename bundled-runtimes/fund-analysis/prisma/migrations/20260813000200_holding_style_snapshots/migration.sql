CREATE TABLE IF NOT EXISTS "holding_style_snapshots" (
    "wind_code" VARCHAR(20) NOT NULL,
    "quarter" VARCHAR(10) NOT NULL,
    "peer_group_id" TEXT,
    "peer_group_key" TEXT,
    "peer_group_name" TEXT,
    "descriptors" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "peer_percentiles" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "style_labels" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "peer_sample_size" INTEGER NOT NULL DEFAULT 0,
    "minimum_peer_count" INTEGER NOT NULL DEFAULT 5,
    "holdings_disclosed_weight" DECIMAL(8,6),
    "source" TEXT NOT NULL,
    "status" VARCHAR(30) NOT NULL,
    "missing_items" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "calculated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "holding_style_snapshots_pkey" PRIMARY KEY ("wind_code", "quarter")
);

CREATE INDEX IF NOT EXISTS "holding_style_snapshots_peer_group_id_quarter_idx"
  ON "holding_style_snapshots"("peer_group_id", "quarter");
