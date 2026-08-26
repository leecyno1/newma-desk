ALTER TABLE "holdings"
  ADD COLUMN IF NOT EXISTS "weight_validation_status" VARCHAR(30);
