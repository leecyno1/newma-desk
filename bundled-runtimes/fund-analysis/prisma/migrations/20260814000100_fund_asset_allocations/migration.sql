CREATE TABLE IF NOT EXISTS "fund_asset_allocations" (
    "wind_code" VARCHAR(20) NOT NULL,
    "report_date" DATE NOT NULL,
    "stock_ratio" DECIMAL(10,8),
    "bond_ratio" DECIMAL(10,8),
    "cash_ratio" DECIMAL(10,8),
    "net_asset_yi" DECIMAL(15,4),
    "source" TEXT NOT NULL,
    "source_url" TEXT,
    "fetched_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "fund_asset_allocations_pkey" PRIMARY KEY ("wind_code", "report_date"),
    CONSTRAINT "fund_asset_allocations_wind_code_fkey"
      FOREIGN KEY ("wind_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "fund_asset_allocations_report_date_idx"
  ON "fund_asset_allocations"("report_date");
