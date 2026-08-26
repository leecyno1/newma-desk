-- Explainable peer group foundation for fund research comparison.

CREATE TABLE "peer_groups" (
    "id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "strategy_family_id" TEXT,
    "asset_class" TEXT NOT NULL,
    "active_passive" TEXT NOT NULL,
    "benchmark_code" TEXT,
    "benchmark_name" TEXT,
    "inclusion_rules" JSONB NOT NULL,
    "exclusion_rules" JSONB,
    "minimum_peer_count" INTEGER NOT NULL DEFAULT 10,
    "source" TEXT NOT NULL DEFAULT 'peer_group_policy',
    "source_updated_at" DATE,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "peer_groups_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "peer_group_members" (
    "id" TEXT NOT NULL,
    "peer_group_id" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'member',
    "matched_rules" JSONB NOT NULL,
    "excluded_rules" JSONB,
    "sample_as_of_date" DATE,
    "confidence" DECIMAL(5,2),
    "source" TEXT NOT NULL DEFAULT 'peer_group_builder',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "peer_group_members_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "peer_groups_key_key" ON "peer_groups"("key");
CREATE INDEX "peer_groups_strategy_family_id_idx" ON "peer_groups"("strategy_family_id");
CREATE INDEX "peer_groups_asset_class_idx" ON "peer_groups"("asset_class");
CREATE INDEX "peer_groups_active_passive_idx" ON "peer_groups"("active_passive");
CREATE INDEX "peer_groups_benchmark_code_idx" ON "peer_groups"("benchmark_code");

CREATE UNIQUE INDEX "peer_group_members_peer_group_id_entity_id_key" ON "peer_group_members"("peer_group_id", "entity_id");
CREATE INDEX "peer_group_members_peer_group_id_idx" ON "peer_group_members"("peer_group_id");
CREATE INDEX "peer_group_members_entity_id_idx" ON "peer_group_members"("entity_id");
CREATE INDEX "peer_group_members_role_idx" ON "peer_group_members"("role");

ALTER TABLE "peer_groups"
  ADD CONSTRAINT "peer_groups_strategy_family_id_fkey"
  FOREIGN KEY ("strategy_family_id") REFERENCES "strategy_families"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "peer_group_members"
  ADD CONSTRAINT "peer_group_members_peer_group_id_fkey"
  FOREIGN KEY ("peer_group_id") REFERENCES "peer_groups"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "peer_group_members"
  ADD CONSTRAINT "peer_group_members_entity_id_fkey"
  FOREIGN KEY ("entity_id") REFERENCES "fund_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;
