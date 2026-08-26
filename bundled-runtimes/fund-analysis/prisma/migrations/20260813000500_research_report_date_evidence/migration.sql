ALTER TABLE research_reports
ADD COLUMN IF NOT EXISTS report_date_source VARCHAR(30),
ADD COLUMN IF NOT EXISTS report_date_precision VARCHAR(20);
