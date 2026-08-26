-- Manager research loop foundation:
-- tenure slicing, co-management split, representative attribution,
-- style drift, departure/succession impact, and platform contribution.

CREATE TABLE "manager_tenure_slices" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT NOT NULL,
    "fund_code" TEXT NOT NULL,
    "fund_name" TEXT,
    "role" TEXT NOT NULL DEFAULT 'lead',
    "co_manager_names" TEXT[],
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "tenure_days" INTEGER,
    "overlap_share" DECIMAL(5,2),
    "performance_snapshot" JSONB,
    "attribution_notes" TEXT,
    "evidence_refs" JSONB,
    "source" TEXT NOT NULL DEFAULT 'manager_tenure_policy',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "manager_tenure_slices_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "manager_representative_attributions" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT NOT NULL,
    "fund_code" TEXT NOT NULL,
    "fund_name" TEXT,
    "period_start" DATE NOT NULL,
    "period_end" DATE NOT NULL,
    "excess_return" DECIMAL(10,4),
    "max_drawdown" DECIMAL(10,4),
    "attribution_summary" JSONB,
    "style_drift_score" DECIMAL(5,2),
    "platform_contribution" DECIMAL(5,2),
    "conclusion" TEXT,
    "evidence_refs" JSONB,
    "quality_status" TEXT NOT NULL DEFAULT 'draft',
    "source" TEXT NOT NULL DEFAULT 'manager_representative_attribution',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "manager_representative_attributions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "manager_transition_events" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT NOT NULL,
    "fund_code" TEXT,
    "event_date" DATE NOT NULL,
    "event_type" TEXT NOT NULL,
    "previous_manager_names" TEXT[],
    "next_manager_names" TEXT[],
    "impact_window_days" INTEGER,
    "impact_snapshot" JSONB,
    "research_implication" TEXT,
    "evidence_refs" JSONB,
    "source" TEXT NOT NULL DEFAULT 'manager_transition_policy',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "manager_transition_events_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "manager_tenure_slices_manager_id_fund_code_start_date_key"
  ON "manager_tenure_slices"("manager_id", "fund_code", "start_date");
CREATE INDEX "manager_tenure_slices_manager_id_idx" ON "manager_tenure_slices"("manager_id");
CREATE INDEX "manager_tenure_slices_fund_code_idx" ON "manager_tenure_slices"("fund_code");
CREATE INDEX "manager_tenure_slices_role_idx" ON "manager_tenure_slices"("role");

CREATE UNIQUE INDEX "manager_representative_unique_period"
  ON "manager_representative_attributions"("manager_id", "fund_code", "period_start", "period_end");
CREATE INDEX "manager_representative_attributions_manager_id_idx"
  ON "manager_representative_attributions"("manager_id");
CREATE INDEX "manager_representative_attributions_fund_code_idx"
  ON "manager_representative_attributions"("fund_code");
CREATE INDEX "manager_representative_attributions_quality_status_idx"
  ON "manager_representative_attributions"("quality_status");

CREATE INDEX "manager_transition_events_manager_id_event_date_idx"
  ON "manager_transition_events"("manager_id", "event_date");
CREATE INDEX "manager_transition_events_fund_code_idx"
  ON "manager_transition_events"("fund_code");
CREATE INDEX "manager_transition_events_event_type_idx"
  ON "manager_transition_events"("event_type");

ALTER TABLE "manager_tenure_slices"
  ADD CONSTRAINT "manager_tenure_slices_manager_id_fkey"
  FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "manager_representative_attributions"
  ADD CONSTRAINT "manager_representative_attributions_manager_id_fkey"
  FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "manager_transition_events"
  ADD CONSTRAINT "manager_transition_events_manager_id_fkey"
  FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE CASCADE ON UPDATE CASCADE;
