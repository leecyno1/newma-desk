ALTER TABLE research_reports
ADD COLUMN IF NOT EXISTS viewpoint_topics TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
ADD COLUMN IF NOT EXISTS research_domains TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

CREATE INDEX IF NOT EXISTS idx_reports_viewpoint_topics
ON research_reports USING GIN(viewpoint_topics);

CREATE INDEX IF NOT EXISTS idx_reports_research_domains
ON research_reports USING GIN(research_domains);
