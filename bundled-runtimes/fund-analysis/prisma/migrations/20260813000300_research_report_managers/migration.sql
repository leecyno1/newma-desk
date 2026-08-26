CREATE TABLE IF NOT EXISTS "research_report_managers" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "report_id" TEXT NOT NULL,
    "manager_id" VARCHAR(50) NOT NULL,
    "manager_name" VARCHAR(100) NOT NULL,
    "source" VARCHAR(100) NOT NULL DEFAULT 'research_memo_review',
    "confirmed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "research_report_managers_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "research_report_managers_report_id_fkey"
      FOREIGN KEY ("report_id") REFERENCES "research_reports"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "research_report_managers_manager_id_fkey"
      FOREIGN KEY ("manager_id") REFERENCES "managers"("wind_code") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "research_report_managers_report_id_manager_id_key"
      UNIQUE ("report_id", "manager_id")
);

CREATE INDEX IF NOT EXISTS "research_report_managers_manager_id_confirmed_at_idx"
  ON "research_report_managers"("manager_id", "confirmed_at");

INSERT INTO "research_report_managers" (
    "report_id", "manager_id", "manager_name", "source", "confirmed_at"
)
SELECT
    report.id,
    report.manager_id,
    COALESCE(NULLIF(report.manager_name, ''), manager.name),
    'legacy_research_reports.manager_id',
    COALESCE(report.updated_at, report.created_at, CURRENT_TIMESTAMP)
FROM "research_reports" report
JOIN "managers" manager ON manager.wind_code = report.manager_id
WHERE NULLIF(report.manager_id, '') IS NOT NULL
ON CONFLICT ("report_id", "manager_id") DO NOTHING;
