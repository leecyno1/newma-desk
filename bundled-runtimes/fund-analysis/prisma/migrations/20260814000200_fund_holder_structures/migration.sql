CREATE TABLE IF NOT EXISTS "fund_holder_structures" (
    "wind_code" VARCHAR(20) NOT NULL,
    "report_date" DATE NOT NULL,
    "institution_ratio" DECIMAL(10,8),
    "individual_ratio" DECIMAL(10,8),
    "internal_ratio" DECIMAL(10,8),
    "total_shares_yi" DECIMAL(15,4),
    "source" TEXT NOT NULL,
    "source_url" TEXT,
    "fetched_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "fund_holder_structures_pkey" PRIMARY KEY ("wind_code", "report_date"),
    CONSTRAINT "fund_holder_structures_wind_code_fkey"
      FOREIGN KEY ("wind_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "fund_holder_structures_report_date_idx"
  ON "fund_holder_structures"("report_date");
