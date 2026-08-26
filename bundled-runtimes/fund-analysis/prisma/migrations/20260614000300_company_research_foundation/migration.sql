-- Fund company research foundation:
-- product lines, research team, platform capability, issuance/liquidation/scale changes,
-- and same-company product review.

CREATE TABLE "fund_company_research_profiles" (
    "id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "research_team" TEXT,
    "platform_capability" JSONB,
    "product_line_summary" JSONB,
    "issuance_summary" JSONB,
    "liquidation_summary" JSONB,
    "scale_trend" JSONB,
    "manager_bench" JSONB,
    "same_company_review" JSONB,
    "evidence_refs" JSONB,
    "quality_status" TEXT NOT NULL DEFAULT 'draft',
    "source" TEXT NOT NULL DEFAULT 'company_research_profile',
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_company_research_profiles_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_product_line_research_snapshots" (
    "id" TEXT NOT NULL,
    "product_line_id" TEXT NOT NULL,
    "as_of_date" DATE NOT NULL,
    "fund_count" INTEGER,
    "active_fund_count" INTEGER,
    "total_asset" DECIMAL(18,2),
    "flagship_fund_codes" TEXT[],
    "average_excess_return" DECIMAL(10,4),
    "liquidation_count" INTEGER,
    "issuance_count" INTEGER,
    "review_summary" TEXT,
    "evidence_refs" JSONB,
    "source" TEXT NOT NULL DEFAULT 'product_line_research',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_product_line_research_snapshots_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fund_company_research_events" (
    "id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "event_date" DATE NOT NULL,
    "event_type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "affected_product_line_id" TEXT,
    "affected_fund_codes" TEXT[],
    "research_impact" TEXT,
    "evidence_refs" JSONB,
    "source" TEXT NOT NULL DEFAULT 'company_research_event',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fund_company_research_events_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "fund_company_research_profiles_company_id_key"
  ON "fund_company_research_profiles"("company_id");
CREATE INDEX "fund_company_research_profiles_quality_status_idx"
  ON "fund_company_research_profiles"("quality_status");

CREATE UNIQUE INDEX "fund_product_line_research_snapshots_product_line_id_as_of_date_key"
  ON "fund_product_line_research_snapshots"("product_line_id", "as_of_date");
CREATE INDEX "fund_product_line_research_snapshots_product_line_id_idx"
  ON "fund_product_line_research_snapshots"("product_line_id");
CREATE INDEX "fund_product_line_research_snapshots_as_of_date_idx"
  ON "fund_product_line_research_snapshots"("as_of_date");

CREATE INDEX "fund_company_research_events_company_id_event_date_idx"
  ON "fund_company_research_events"("company_id", "event_date");
CREATE INDEX "fund_company_research_events_event_type_idx"
  ON "fund_company_research_events"("event_type");
CREATE INDEX "fund_company_research_events_affected_product_line_id_idx"
  ON "fund_company_research_events"("affected_product_line_id");

ALTER TABLE "fund_company_research_profiles"
  ADD CONSTRAINT "fund_company_research_profiles_company_id_fkey"
  FOREIGN KEY ("company_id") REFERENCES "fund_companies"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "fund_product_line_research_snapshots"
  ADD CONSTRAINT "fund_product_line_research_snapshots_product_line_id_fkey"
  FOREIGN KEY ("product_line_id") REFERENCES "fund_product_lines"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "fund_company_research_events"
  ADD CONSTRAINT "fund_company_research_events_company_id_fkey"
  FOREIGN KEY ("company_id") REFERENCES "fund_companies"("id") ON DELETE CASCADE ON UPDATE CASCADE;
