-- Fund research entity standardization foundation.
-- This layer separates canonical research objects from share classes,
-- product lines, strategy families, lifecycle events, and change history.

CREATE TABLE "fund_companies" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "normalized_name" TEXT NOT NULL,
    "short_name" TEXT,
    "source" TEXT NOT NULL DEFAULT 'manual_or_sync',
    "source_updated_at" DATE,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_companies_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "strategy_families" (
    "id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "asset_class" TEXT,
    "active_passive" TEXT,
    "style_tags" TEXT[],
    "benchmark_policy" JSONB,
    "peer_policy" JSONB,
    "source" TEXT NOT NULL DEFAULT 'methodology_config',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "strategy_families_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_product_lines" (
    "id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "asset_class" TEXT,
    "strategy_family_id" TEXT,
    "description" TEXT,
    "source" TEXT NOT NULL DEFAULT 'manual_or_sync',
    "source_updated_at" DATE,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_product_lines_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_entities" (
    "id" TEXT NOT NULL,
    "canonical_code" TEXT NOT NULL,
    "canonical_name" TEXT NOT NULL,
    "normalized_name" TEXT NOT NULL,
    "company_id" TEXT,
    "product_line_id" TEXT,
    "strategy_family_id" TEXT,
    "asset_class" TEXT,
    "active_passive" TEXT,
    "lifecycle_stage" TEXT NOT NULL DEFAULT 'active',
    "established_at" DATE,
    "terminated_at" DATE,
    "source" TEXT NOT NULL DEFAULT 'entity_standardization',
    "source_updated_at" DATE,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_entities_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_share_classes" (
    "id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "fund_id" TEXT,
    "wind_code" TEXT NOT NULL,
    "share_class" TEXT,
    "fee_class" TEXT,
    "currency" TEXT DEFAULT 'CNY',
    "is_primary" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'active',
    "source" TEXT NOT NULL DEFAULT 'share_class_normalizer',
    "source_updated_at" DATE,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_share_classes_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_lifecycle_events" (
    "id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "event_date" DATE NOT NULL,
    "event_type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "source" TEXT NOT NULL,
    "evidence_ref" TEXT,
    "metadata" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fund_lifecycle_events_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_change_history" (
    "id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "changed_at" DATE NOT NULL,
    "change_type" TEXT NOT NULL,
    "field_name" TEXT,
    "previous_value" TEXT,
    "new_value" TEXT,
    "source" TEXT NOT NULL,
    "evidence_ref" TEXT,
    "metadata" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fund_change_history_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "fund_companies_name_key" ON "fund_companies"("name");
CREATE INDEX "fund_companies_normalized_name_idx" ON "fund_companies"("normalized_name");

CREATE UNIQUE INDEX "strategy_families_key_key" ON "strategy_families"("key");
CREATE INDEX "strategy_families_asset_class_idx" ON "strategy_families"("asset_class");
CREATE INDEX "strategy_families_active_passive_idx" ON "strategy_families"("active_passive");

CREATE UNIQUE INDEX "fund_product_lines_company_id_name_key" ON "fund_product_lines"("company_id", "name");
CREATE INDEX "fund_product_lines_company_id_idx" ON "fund_product_lines"("company_id");
CREATE INDEX "fund_product_lines_strategy_family_id_idx" ON "fund_product_lines"("strategy_family_id");

CREATE UNIQUE INDEX "fund_entities_canonical_code_key" ON "fund_entities"("canonical_code");
CREATE INDEX "fund_entities_normalized_name_idx" ON "fund_entities"("normalized_name");
CREATE INDEX "fund_entities_company_id_idx" ON "fund_entities"("company_id");
CREATE INDEX "fund_entities_product_line_id_idx" ON "fund_entities"("product_line_id");
CREATE INDEX "fund_entities_strategy_family_id_idx" ON "fund_entities"("strategy_family_id");
CREATE INDEX "fund_entities_asset_class_idx" ON "fund_entities"("asset_class");
CREATE INDEX "fund_entities_lifecycle_stage_idx" ON "fund_entities"("lifecycle_stage");

CREATE UNIQUE INDEX "fund_share_classes_wind_code_key" ON "fund_share_classes"("wind_code");
CREATE INDEX "fund_share_classes_entity_id_idx" ON "fund_share_classes"("entity_id");
CREATE INDEX "fund_share_classes_fund_id_idx" ON "fund_share_classes"("fund_id");
CREATE INDEX "fund_share_classes_share_class_idx" ON "fund_share_classes"("share_class");
CREATE INDEX "fund_share_classes_status_idx" ON "fund_share_classes"("status");

CREATE INDEX "fund_lifecycle_events_entity_id_event_date_idx" ON "fund_lifecycle_events"("entity_id", "event_date");
CREATE INDEX "fund_lifecycle_events_event_type_idx" ON "fund_lifecycle_events"("event_type");

CREATE INDEX "fund_change_history_entity_id_changed_at_idx" ON "fund_change_history"("entity_id", "changed_at");
CREATE INDEX "fund_change_history_change_type_idx" ON "fund_change_history"("change_type");

ALTER TABLE "fund_product_lines"
  ADD CONSTRAINT "fund_product_lines_company_id_fkey"
  FOREIGN KEY ("company_id") REFERENCES "fund_companies"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "fund_product_lines"
  ADD CONSTRAINT "fund_product_lines_strategy_family_id_fkey"
  FOREIGN KEY ("strategy_family_id") REFERENCES "strategy_families"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "fund_entities"
  ADD CONSTRAINT "fund_entities_company_id_fkey"
  FOREIGN KEY ("company_id") REFERENCES "fund_companies"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "fund_entities"
  ADD CONSTRAINT "fund_entities_product_line_id_fkey"
  FOREIGN KEY ("product_line_id") REFERENCES "fund_product_lines"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "fund_entities"
  ADD CONSTRAINT "fund_entities_strategy_family_id_fkey"
  FOREIGN KEY ("strategy_family_id") REFERENCES "strategy_families"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "fund_share_classes"
  ADD CONSTRAINT "fund_share_classes_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "fund_share_classes"
  ADD CONSTRAINT "fund_share_classes_fund_id_fkey"
  FOREIGN KEY ("fund_id") REFERENCES "funds"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "fund_lifecycle_events"
  ADD CONSTRAINT "fund_lifecycle_events_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "fund_change_history"
  ADD CONSTRAINT "fund_change_history_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;
