-- Keep manager investment-framework conclusions separate from broader philosophy fields.
ALTER TABLE "manager_profiles"
  ADD COLUMN IF NOT EXISTS "product_positioning" TEXT,
  ADD COLUMN IF NOT EXISTS "investment_objective" TEXT,
  ADD COLUMN IF NOT EXISTS "investment_method" TEXT;
