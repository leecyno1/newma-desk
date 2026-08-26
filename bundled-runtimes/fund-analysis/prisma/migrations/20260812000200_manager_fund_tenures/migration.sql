CREATE TABLE IF NOT EXISTS "manager_fund_tenures" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "manager_id" VARCHAR(50) NOT NULL,
    "fund_code" VARCHAR(20) NOT NULL,
    "fund_name" VARCHAR(200),
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "is_current" BOOLEAN NOT NULL DEFAULT false,
    "performance_snapshot" JSONB,
    "source" VARCHAR(100) NOT NULL DEFAULT 'tushare.fund_manager',
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "manager_fund_tenures_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "manager_fund_tenures_manager_id_fkey"
      FOREIGN KEY ("manager_id") REFERENCES "managers"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "manager_fund_tenures_fund_code_fkey"
      FOREIGN KEY ("fund_code") REFERENCES "funds"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "manager_fund_tenures_manager_id_fund_code_start_date_key"
      UNIQUE ("manager_id", "fund_code", "start_date")
);

CREATE INDEX IF NOT EXISTS "manager_fund_tenures_manager_id_is_current_idx"
  ON "manager_fund_tenures"("manager_id", "is_current");
CREATE INDEX IF NOT EXISTS "manager_fund_tenures_fund_code_idx"
  ON "manager_fund_tenures"("fund_code");
