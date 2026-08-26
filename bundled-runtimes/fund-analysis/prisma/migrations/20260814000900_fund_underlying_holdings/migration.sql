CREATE TABLE IF NOT EXISTS "fund_underlying_holdings" (
  "wind_code" VARCHAR(20) NOT NULL REFERENCES "funds"("wind_code") ON DELETE CASCADE,
  "report_date" DATE NOT NULL,
  "sequence" INTEGER NOT NULL,
  "underlying_fund_code" VARCHAR(20) NOT NULL,
  "underlying_fund_name" VARCHAR(200) NOT NULL,
  "nav_ratio" DECIMAL(10, 8),
  "daily_return" DECIMAL(10, 8),
  "source" TEXT NOT NULL,
  "source_url" TEXT,
  "fetched_at" TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT "fund_underlying_holdings_pkey"
    PRIMARY KEY ("wind_code", "report_date", "underlying_fund_code")
);

CREATE INDEX IF NOT EXISTS "idx_fund_underlying_holdings_report_date"
  ON "fund_underlying_holdings"("report_date");
CREATE INDEX IF NOT EXISTS "idx_fund_underlying_holdings_code"
  ON "fund_underlying_holdings"("underlying_fund_code");
