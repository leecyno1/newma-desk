-- CreateExtension

-- CreateTable
CREATE TABLE "funds" (
    "id" TEXT NOT NULL,
    "wind_code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "manager_ids" TEXT[],
    "nav" DECIMAL(10,4),
    "nav_date" DATE,
    "total_asset" DECIMAL(15,2),
    "establishment_date" DATE,
    "performance_data" JSONB,
    "risk_metrics" JSONB,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "funds_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "managers" (
    "id" TEXT NOT NULL,
    "wind_code" TEXT,
    "name" TEXT NOT NULL,
    "company" TEXT,
    "education" TEXT,
    "work_years" INTEGER,
    "management_years" DECIMAL(5,2),
    "current_funds" TEXT[],
    "historical_performance" JSONB,
    "style_analysis" JSONB,
    "raw_data" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "managers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "research_reports" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT,
    "fund_ids" TEXT[],
    "title" TEXT NOT NULL,
    "report_date" DATE NOT NULL,
    "source" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "summary" TEXT,
    "key_points" JSONB,
    "tags" TEXT[],
    "embedding" vector(1536),
    "attachments" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "research_reports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_analysis_reports" (
    "id" TEXT NOT NULL,
    "target_type" TEXT NOT NULL,
    "target_id" TEXT NOT NULL,
    "report_type" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "data_sources" JSONB,
    "research_reports_used" TEXT[],
    "generation_params" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ai_analysis_reports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scores" (
    "id" TEXT NOT NULL,
    "target_type" TEXT NOT NULL,
    "target_id" TEXT NOT NULL,
    "dimension" TEXT NOT NULL,
    "score" DECIMAL(5,2) NOT NULL,
    "weight" DECIMAL(3,2),
    "calculation_method" TEXT NOT NULL,
    "details" JSONB,
    "scored_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "scores_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "screening_criteria" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "criteria" JSONB NOT NULL,
    "created_by" TEXT,
    "is_public" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "screening_criteria_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "holdings" (
    "id" TEXT NOT NULL,
    "fund_id" TEXT NOT NULL,
    "stock_code" TEXT NOT NULL,
    "stock_name" TEXT NOT NULL,
    "weight" DECIMAL(8,4) NOT NULL,
    "quarter" TEXT NOT NULL,
    "market_cap" TEXT,
    "pe_ratio" DECIMAL(10,2),
    "pb_ratio" DECIMAL(10,2),
    "roe" DECIMAL(8,4),
    "revenue_growth" DECIMAL(10,4),
    "industry" TEXT,
    "sub_industry" TEXT,
    "dividend_yield" DECIMAL(8,4),
    "market_cap_value" DECIMAL(15,2),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "holdings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "holding_factors" (
    "id" TEXT NOT NULL,
    "holding_id" TEXT NOT NULL,
    "factor_name" TEXT NOT NULL,
    "factor_value" DECIMAL(10,4) NOT NULL,

    CONSTRAINT "holding_factors_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "factor_exposures" (
    "id" TEXT NOT NULL,
    "fund_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "factor_name" TEXT NOT NULL,
    "exposure" DECIMAL(10,4) NOT NULL,
    "factor_return" DECIMAL(10,4),
    "risk_contribution" DECIMAL(8,4),

    CONSTRAINT "factor_exposures_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "performance_attributions" (
    "id" TEXT NOT NULL,
    "fund_id" TEXT NOT NULL,
    "benchmark_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "total_return" DECIMAL(10,4) NOT NULL,
    "benchmark_return" DECIMAL(10,4) NOT NULL,
    "active_return" DECIMAL(10,4) NOT NULL,
    "allocation_effect" DECIMAL(10,4),
    "selection_effect" DECIMAL(10,4),
    "interaction_effect" DECIMAL(10,4),
    "industry_allocation" DECIMAL(10,4),
    "stock_selection" DECIMAL(10,4),
    "residual" DECIMAL(10,4),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "performance_attributions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "manager_profiles" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT NOT NULL,
    "last_updated" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "core_philosophy" TEXT,
    "stock_selection_logic" TEXT,
    "risk_philosophy" TEXT,
    "focus_industries" TEXT[],
    "competence_advantages" TEXT,
    "competence_boundaries" TEXT,
    "style_label" TEXT,
    "concentration" TEXT,
    "turnover" TEXT,
    "style_stability" INTEGER,
    "philosophy_score" INTEGER,
    "competence_score" INTEGER,
    "style_score" INTEGER,
    "overall_quality_score" INTEGER,
    "philosophy_behavior_consistency" DECIMAL(5,2),
    "valuation_consistency" INTEGER,
    "quality_consistency" INTEGER,
    "industry_consistency" INTEGER,
    "key_insights" TEXT[],
    "red_flags" TEXT[],
    "interviews_analyzed" INTEGER NOT NULL DEFAULT 0,
    "last_interview_date" TIMESTAMP(3),

    CONSTRAINT "manager_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "philosophy_tracking" (
    "id" TEXT NOT NULL,
    "manager_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "philosophy_summary" TEXT NOT NULL,
    "consistency_score" DECIMAL(5,2) NOT NULL,
    "style_label" TEXT,
    "pe_focus" TEXT,
    "roe_focus" TEXT,

    CONSTRAINT "philosophy_tracking_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "factor_returns" (
    "id" TEXT NOT NULL,
    "factor_name" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "return" DECIMAL(10,4) NOT NULL,

    CONSTRAINT "factor_returns_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "industry_returns" (
    "id" TEXT NOT NULL,
    "industry" TEXT NOT NULL,
    "benchmark_id" TEXT NOT NULL,
    "quarter" TEXT NOT NULL,
    "fund_return" DECIMAL(10,4) NOT NULL,
    "bench_return" DECIMAL(10,4) NOT NULL,
    "active_return" DECIMAL(10,4) NOT NULL,

    CONSTRAINT "industry_returns_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "funds_wind_code_key" ON "funds"("wind_code");

-- CreateIndex
CREATE INDEX "funds_wind_code_idx" ON "funds"("wind_code");

-- CreateIndex
CREATE INDEX "funds_name_idx" ON "funds"("name");

-- CreateIndex
CREATE INDEX "funds_type_idx" ON "funds"("type");

-- CreateIndex
CREATE UNIQUE INDEX "managers_wind_code_key" ON "managers"("wind_code");

-- CreateIndex
CREATE INDEX "managers_name_idx" ON "managers"("name");

-- CreateIndex
CREATE INDEX "managers_company_idx" ON "managers"("company");

-- CreateIndex
CREATE INDEX "research_reports_manager_id_idx" ON "research_reports"("manager_id");

-- CreateIndex
CREATE INDEX "research_reports_report_date_idx" ON "research_reports"("report_date");

-- CreateIndex
CREATE INDEX "research_reports_tags_idx" ON "research_reports"("tags");

-- CreateIndex
CREATE INDEX "ai_analysis_reports_target_type_target_id_idx" ON "ai_analysis_reports"("target_type", "target_id");

-- CreateIndex
CREATE INDEX "ai_analysis_reports_report_type_idx" ON "ai_analysis_reports"("report_type");

-- CreateIndex
CREATE INDEX "ai_analysis_reports_created_at_idx" ON "ai_analysis_reports"("created_at");

-- CreateIndex
CREATE INDEX "scores_target_type_target_id_idx" ON "scores"("target_type", "target_id");

-- CreateIndex
CREATE INDEX "scores_dimension_idx" ON "scores"("dimension");

-- CreateIndex
CREATE INDEX "scores_scored_at_idx" ON "scores"("scored_at");

-- CreateIndex
CREATE INDEX "screening_criteria_created_by_idx" ON "screening_criteria"("created_by");

-- CreateIndex
CREATE INDEX "screening_criteria_is_public_idx" ON "screening_criteria"("is_public");

-- CreateIndex
CREATE INDEX "holdings_fund_id_quarter_idx" ON "holdings"("fund_id", "quarter");

-- CreateIndex
CREATE INDEX "holdings_industry_idx" ON "holdings"("industry");

-- CreateIndex
CREATE INDEX "holdings_stock_code_idx" ON "holdings"("stock_code");

-- CreateIndex
CREATE UNIQUE INDEX "holdings_fund_id_quarter_stock_code_key" ON "holdings"("fund_id", "quarter", "stock_code");

-- CreateIndex
CREATE UNIQUE INDEX "holding_factors_holding_id_factor_name_key" ON "holding_factors"("holding_id", "factor_name");

-- CreateIndex
CREATE INDEX "factor_exposures_fund_id_quarter_idx" ON "factor_exposures"("fund_id", "quarter");

-- CreateIndex
CREATE UNIQUE INDEX "factor_exposures_fund_id_quarter_factor_name_key" ON "factor_exposures"("fund_id", "quarter", "factor_name");

-- CreateIndex
CREATE INDEX "performance_attributions_fund_id_quarter_idx" ON "performance_attributions"("fund_id", "quarter");

-- CreateIndex
CREATE UNIQUE INDEX "performance_attributions_fund_id_quarter_key" ON "performance_attributions"("fund_id", "quarter");

-- CreateIndex
CREATE UNIQUE INDEX "manager_profiles_manager_id_key" ON "manager_profiles"("manager_id");

-- CreateIndex
CREATE INDEX "philosophy_tracking_manager_id_idx" ON "philosophy_tracking"("manager_id");

-- CreateIndex
CREATE UNIQUE INDEX "philosophy_tracking_manager_id_quarter_key" ON "philosophy_tracking"("manager_id", "quarter");

-- CreateIndex
CREATE INDEX "factor_returns_factor_name_idx" ON "factor_returns"("factor_name");

-- CreateIndex
CREATE UNIQUE INDEX "factor_returns_factor_name_date_key" ON "factor_returns"("factor_name", "date");

-- CreateIndex
CREATE INDEX "industry_returns_industry_idx" ON "industry_returns"("industry");

-- CreateIndex
CREATE UNIQUE INDEX "industry_returns_industry_benchmark_id_quarter_key" ON "industry_returns"("industry", "benchmark_id", "quarter");

-- AddForeignKey
ALTER TABLE "research_reports" ADD CONSTRAINT "research_reports_manager_id_fkey" FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_analysis_reports" ADD CONSTRAINT "ai_analysis_fund_fk" FOREIGN KEY ("target_id") REFERENCES "funds"("id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "ai_analysis_reports" ADD CONSTRAINT "ai_analysis_manager_fk" FOREIGN KEY ("target_id") REFERENCES "managers"("id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "score_fund_fk" FOREIGN KEY ("target_id") REFERENCES "funds"("id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "score_manager_fk" FOREIGN KEY ("target_id") REFERENCES "managers"("id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "holdings" ADD CONSTRAINT "holdings_fund_id_fkey" FOREIGN KEY ("fund_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "holding_factors" ADD CONSTRAINT "holding_factors_holding_id_fkey" FOREIGN KEY ("holding_id") REFERENCES "holdings"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "factor_exposures" ADD CONSTRAINT "factor_exposures_fund_id_fkey" FOREIGN KEY ("fund_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "performance_attributions" ADD CONSTRAINT "performance_attributions_fund_id_fkey" FOREIGN KEY ("fund_id") REFERENCES "funds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "manager_profiles" ADD CONSTRAINT "manager_profiles_manager_id_fkey" FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "philosophy_tracking" ADD CONSTRAINT "philosophy_tracking_manager_id_fkey" FOREIGN KEY ("manager_id") REFERENCES "managers"("id") ON DELETE CASCADE ON UPDATE CASCADE;
