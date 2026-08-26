ALTER TABLE "fund_bond_holdings"
  ADD COLUMN IF NOT EXISTS "issuer" VARCHAR(300),
  ADD COLUMN IF NOT EXISTS "security_bond_type" VARCHAR(100),
  ADD COLUMN IF NOT EXISTS "credit_rating" VARCHAR(30),
  ADD COLUMN IF NOT EXISTS "rating_type" VARCHAR(30),
  ADD COLUMN IF NOT EXISTS "maturity_date" DATE,
  ADD COLUMN IF NOT EXISTS "coupon_rate" DECIMAL(10,8),
  ADD COLUMN IF NOT EXISTS "metadata_source" TEXT,
  ADD COLUMN IF NOT EXISTS "metadata_url" TEXT,
  ADD COLUMN IF NOT EXISTS "metadata_status" VARCHAR(30) NOT NULL DEFAULT 'unavailable';

CREATE INDEX IF NOT EXISTS "fund_bond_holdings_bond_code_idx"
  ON "fund_bond_holdings"("bond_code");
