CREATE TABLE IF NOT EXISTS "market_index_constituent_snapshots" (
  "index_code" VARCHAR(30) NOT NULL,
  "as_of_date" DATE NOT NULL,
  "constituent_code" VARCHAR(20) NOT NULL,
  "constituent_name" VARCHAR(200),
  "weight" DECIMAL(12,10),
  "industry" VARCHAR(100),
  "source" TEXT NOT NULL,
  "evidence_url" TEXT,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "market_index_constituent_snapshots_pkey"
    PRIMARY KEY ("index_code", "as_of_date", "constituent_code")
);

CREATE INDEX IF NOT EXISTS "market_index_snapshot_date_idx"
  ON "market_index_constituent_snapshots"("index_code", "as_of_date" DESC);
