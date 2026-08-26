CREATE TABLE IF NOT EXISTS "bond_index_series" (
  "series_key" VARCHAR(100) NOT NULL,
  "index_group" VARCHAR(50) NOT NULL,
  "index_name" VARCHAR(200) NOT NULL,
  "index_id" VARCHAR(64) NOT NULL,
  "period_code" VARCHAR(10) NOT NULL,
  "period_label" VARCHAR(30) NOT NULL,
  "indicator" VARCHAR(30) NOT NULL,
  "trade_date" DATE NOT NULL,
  "value" DECIMAL(18,8) NOT NULL,
  "source" TEXT NOT NULL,
  "source_url" TEXT NOT NULL,
  "fetched_at" TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT "bond_index_series_pkey" PRIMARY KEY ("series_key", "indicator", "trade_date")
);

CREATE TABLE IF NOT EXISTS "fund_bond_duration_estimates" (
  "wind_code" VARCHAR(20) NOT NULL,
  "as_of_date" DATE NOT NULL,
  "window_weeks" INTEGER NOT NULL,
  "data_start" DATE,
  "data_end" DATE,
  "observations" INTEGER NOT NULL DEFAULT 0,
  "estimated_duration" DECIMAL(10,6),
  "duration_bucket" VARCHAR(50),
  "r_squared" DECIMAL(10,8),
  "tracking_error" DECIMAL(10,8),
  "selected_series" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "weights" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "group_diagnostics" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "methodology_version" VARCHAR(80) NOT NULL,
  "status" VARCHAR(30) NOT NULL,
  "source" TEXT NOT NULL,
  "missing_items" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "calculated_at" TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT "fund_bond_duration_estimates_pkey" PRIMARY KEY ("wind_code", "as_of_date", "window_weeks"),
  CONSTRAINT "fund_bond_duration_estimates_wind_code_fkey" FOREIGN KEY ("wind_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "bond_index_series_group_date_idx"
  ON "bond_index_series"("index_group", "trade_date");
CREATE INDEX IF NOT EXISTS "bond_index_series_indicator_date_idx"
  ON "bond_index_series"("indicator", "trade_date");
CREATE INDEX IF NOT EXISTS "fund_bond_duration_estimates_latest_idx"
  ON "fund_bond_duration_estimates"("wind_code", "as_of_date" DESC);
