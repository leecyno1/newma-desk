-- Methodology configuration foundation:
-- separate research templates for active equity, fixed income, index, QDII, FOF, and quant funds.

CREATE TABLE "research_methodology_templates" (
    "id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "fund_type" TEXT NOT NULL,
    "asset_class" TEXT,
    "active_passive" TEXT,
    "description" TEXT,
    "required_evidence" JSONB NOT NULL,
    "benchmark_policy" JSONB,
    "peer_policy" JSONB,
    "attribution_policy" JSONB,
    "holding_policy" JSONB,
    "manager_policy" JSONB,
    "company_policy" JSONB,
    "source" TEXT NOT NULL DEFAULT 'methodology_config',
    "version" TEXT NOT NULL DEFAULT '1.0.0',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "research_methodology_templates_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "research_methodology_dimensions" (
    "id" TEXT NOT NULL,
    "template_id" TEXT NOT NULL,
    "dimension_key" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "weight" DECIMAL(5,2),
    "evidence_fields" TEXT[],
    "calculation_policy" JSONB,
    "hard_gate" BOOLEAN NOT NULL DEFAULT false,
    "display_order" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "research_methodology_dimensions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "research_methodology_mappings" (
    "id" TEXT NOT NULL,
    "template_id" TEXT NOT NULL,
    "strategy_family_id" TEXT,
    "fund_type" TEXT,
    "asset_class" TEXT,
    "active_passive" TEXT,
    "match_rules" JSONB,
    "priority" INTEGER NOT NULL DEFAULT 100,
    "source" TEXT NOT NULL DEFAULT 'methodology_config',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "research_methodology_mappings_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "research_methodology_templates_key_key"
  ON "research_methodology_templates"("key");
CREATE INDEX "research_methodology_templates_fund_type_idx"
  ON "research_methodology_templates"("fund_type");
CREATE INDEX "research_methodology_templates_asset_class_idx"
  ON "research_methodology_templates"("asset_class");
CREATE INDEX "research_methodology_templates_active_passive_idx"
  ON "research_methodology_templates"("active_passive");
CREATE INDEX "research_methodology_templates_is_active_idx"
  ON "research_methodology_templates"("is_active");

CREATE UNIQUE INDEX "research_methodology_dimensions_template_id_dimension_key_key"
  ON "research_methodology_dimensions"("template_id", "dimension_key");
CREATE INDEX "research_methodology_dimensions_template_id_idx"
  ON "research_methodology_dimensions"("template_id");
CREATE INDEX "research_methodology_dimensions_dimension_key_idx"
  ON "research_methodology_dimensions"("dimension_key");
CREATE INDEX "research_methodology_dimensions_hard_gate_idx"
  ON "research_methodology_dimensions"("hard_gate");

CREATE INDEX "research_methodology_mappings_template_id_idx"
  ON "research_methodology_mappings"("template_id");
CREATE INDEX "research_methodology_mappings_strategy_family_id_idx"
  ON "research_methodology_mappings"("strategy_family_id");
CREATE INDEX "research_methodology_mappings_fund_type_idx"
  ON "research_methodology_mappings"("fund_type");
CREATE INDEX "research_methodology_mappings_asset_class_idx"
  ON "research_methodology_mappings"("asset_class");
CREATE INDEX "research_methodology_mappings_active_passive_idx"
  ON "research_methodology_mappings"("active_passive");
CREATE INDEX "research_methodology_mappings_priority_idx"
  ON "research_methodology_mappings"("priority");

ALTER TABLE "research_methodology_dimensions"
  ADD CONSTRAINT "research_methodology_dimensions_template_id_fkey"
  FOREIGN KEY ("template_id") REFERENCES "research_methodology_templates"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "research_methodology_mappings"
  ADD CONSTRAINT "research_methodology_mappings_template_id_fkey"
  FOREIGN KEY ("template_id") REFERENCES "research_methodology_templates"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "research_methodology_mappings"
  ADD CONSTRAINT "research_methodology_mappings_strategy_family_id_fkey"
  FOREIGN KEY ("strategy_family_id") REFERENCES "strategy_families"("id") ON DELETE SET NULL ON UPDATE CASCADE;
