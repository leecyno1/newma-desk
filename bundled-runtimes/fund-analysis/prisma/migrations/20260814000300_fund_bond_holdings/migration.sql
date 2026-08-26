CREATE TABLE IF NOT EXISTS "fund_bond_holdings" (
    "wind_code" VARCHAR(20) NOT NULL,
    "report_date" DATE NOT NULL,
    "sequence" INTEGER NOT NULL,
    "bond_code" VARCHAR(30) NOT NULL,
    "bond_name" VARCHAR(200) NOT NULL,
    "bond_type" VARCHAR(50) NOT NULL,
    "nav_ratio" DECIMAL(10,8),
    "market_value_wan" DECIMAL(18,2),
    "classification_basis" TEXT,
    "source" TEXT NOT NULL,
    "source_url" TEXT,
    "fetched_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "fund_bond_holdings_pkey" PRIMARY KEY ("wind_code", "report_date", "bond_code"),
    CONSTRAINT "fund_bond_holdings_wind_code_fkey"
      FOREIGN KEY ("wind_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "fund_bond_holdings_report_date_idx"
  ON "fund_bond_holdings"("report_date");

CREATE INDEX IF NOT EXISTS "fund_bond_holdings_bond_type_idx"
  ON "fund_bond_holdings"("bond_type");
