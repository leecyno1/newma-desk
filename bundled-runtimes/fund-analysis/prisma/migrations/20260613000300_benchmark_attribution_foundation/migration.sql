-- Benchmark mapping and attribution explanation foundation.

CREATE TABLE "benchmark_mappings" (
    "id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "peer_group_id" TEXT,
    "benchmark_code" TEXT NOT NULL,
    "benchmark_name" TEXT NOT NULL,
    "benchmark_type" TEXT NOT NULL,
    "mapping_method" TEXT NOT NULL,
    "confidence" DECIMAL(5,2),
    "rationale" TEXT NOT NULL,
    "evidence_refs" JSONB,
    "effective_from" DATE,
    "effective_to" DATE,
    "status" TEXT NOT NULL DEFAULT 'active',
    "source" TEXT NOT NULL DEFAULT 'benchmark_mapping_policy',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "benchmark_mappings_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "attribution_explanations" (
    "id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "benchmark_mapping_id" TEXT,
    "period_start" DATE NOT NULL,
    "period_end" DATE NOT NULL,
    "total_return" DECIMAL(10,4),
    "benchmark_return" DECIMAL(10,4),
    "excess_return" DECIMAL(10,4),
    "allocation_effect" DECIMAL(10,4),
    "selection_effect" DECIMAL(10,4),
    "interaction_effect" DECIMAL(10,4),
    "style_contribution" JSONB,
    "industry_contribution" JSONB,
    "asset_allocation" JSONB,
    "residual_explanation" TEXT,
    "evidence_refs" JSONB,
    "quality_status" TEXT NOT NULL DEFAULT 'draft',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "attribution_explanations_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "benchmark_mappings_entity_id_benchmark_code_effective_from_key"
  ON "benchmark_mappings"("entity_id", "benchmark_code", "effective_from");
CREATE INDEX "benchmark_mappings_entity_id_idx" ON "benchmark_mappings"("entity_id");
CREATE INDEX "benchmark_mappings_peer_group_id_idx" ON "benchmark_mappings"("peer_group_id");
CREATE INDEX "benchmark_mappings_benchmark_code_idx" ON "benchmark_mappings"("benchmark_code");
CREATE INDEX "benchmark_mappings_status_idx" ON "benchmark_mappings"("status");

CREATE UNIQUE INDEX "attribution_explanations_unique_period"
  ON "attribution_explanations"("entity_id", "period_start", "period_end", "benchmark_mapping_id");
CREATE INDEX "attribution_explanations_entity_id_period_end_idx" ON "attribution_explanations"("entity_id", "period_end");
CREATE INDEX "attribution_explanations_benchmark_mapping_id_idx" ON "attribution_explanations"("benchmark_mapping_id");
CREATE INDEX "attribution_explanations_quality_status_idx" ON "attribution_explanations"("quality_status");

ALTER TABLE "benchmark_mappings"
  ADD CONSTRAINT "benchmark_mappings_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "benchmark_mappings"
  ADD CONSTRAINT "benchmark_mappings_peer_group_id_fkey"
  FOREIGN KEY ("peer_group_id") REFERENCES "peer_groups"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "attribution_explanations"
  ADD CONSTRAINT "attribution_explanations_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "attribution_explanations"
  ADD CONSTRAINT "attribution_explanations_benchmark_mapping_id_fkey"
  FOREIGN KEY ("benchmark_mapping_id") REFERENCES "benchmark_mappings"("id") ON DELETE SET NULL ON UPDATE CASCADE;
