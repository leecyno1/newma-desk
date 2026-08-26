-- Promote the two most decision-useful memo conclusions to first-class manager profile fields.
ALTER TABLE "manager_profiles"
  ADD COLUMN IF NOT EXISTS "excess_return_source" TEXT,
  ADD COLUMN IF NOT EXISTS "holding_style" TEXT,
  ADD COLUMN IF NOT EXISTS "evidence" JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS "updated_by" VARCHAR(100);

ALTER TABLE "manager_profiles"
  ALTER COLUMN "concentration" TYPE TEXT,
  ALTER COLUMN "turnover" TYPE TEXT;
