CREATE TABLE IF NOT EXISTS benchmark_mappings (
  id text NOT NULL,
  entity_id text NOT NULL,
  peer_group_id text,
  benchmark_code text NOT NULL,
  benchmark_name text NOT NULL,
  benchmark_type text NOT NULL,
  mapping_method text NOT NULL,
  confidence numeric(5,2),
  rationale text NOT NULL,
  evidence_refs jsonb,
  effective_from date,
  effective_to date,
  status text NOT NULL DEFAULT 'active',
  source text NOT NULL DEFAULT 'benchmark_mapping_policy',
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS benchmark_mappings_entity_id_benchmark_code_effective_from_key
  ON benchmark_mappings (entity_id, benchmark_code, effective_from);
CREATE INDEX IF NOT EXISTS benchmark_mappings_entity_id_idx ON benchmark_mappings (entity_id);
CREATE INDEX IF NOT EXISTS benchmark_mappings_peer_group_id_idx ON benchmark_mappings (peer_group_id);
CREATE INDEX IF NOT EXISTS benchmark_mappings_benchmark_code_idx ON benchmark_mappings (benchmark_code);
CREATE INDEX IF NOT EXISTS benchmark_mappings_status_idx ON benchmark_mappings (status);

CREATE TABLE IF NOT EXISTS attribution_explanations (
  id text NOT NULL,
  entity_id text NOT NULL,
  benchmark_mapping_id text,
  period_start date NOT NULL,
  period_end date NOT NULL,
  total_return numeric(10,4),
  benchmark_return numeric(10,4),
  excess_return numeric(10,4),
  allocation_effect numeric(10,4),
  selection_effect numeric(10,4),
  interaction_effect numeric(10,4),
  style_contribution jsonb,
  industry_contribution jsonb,
  asset_allocation jsonb,
  residual_explanation text,
  evidence_refs jsonb,
  quality_status text NOT NULL DEFAULT 'draft',
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS attribution_explanations_unique_period
  ON attribution_explanations (entity_id, period_start, period_end, benchmark_mapping_id);
CREATE INDEX IF NOT EXISTS attribution_explanations_entity_id_period_end_idx ON attribution_explanations (entity_id, period_end);
CREATE INDEX IF NOT EXISTS attribution_explanations_benchmark_mapping_id_idx ON attribution_explanations (benchmark_mapping_id);
CREATE INDEX IF NOT EXISTS attribution_explanations_quality_status_idx ON attribution_explanations (quality_status);

WITH mapping_rows(wind_code, peer_group_key, benchmark_code, benchmark_name, benchmark_type, mapping_method, confidence, rationale, evidence_refs, effective_from) AS (
  VALUES
    ('000002.OF','peer-active-equity-core-large-5y','CSI800','中证800','broad_equity','peer_group_policy',0.88,'按主动权益核心均衡策略族谱、权益资产类别、规模层和同类池映射；用于解释超额收益，不替代合同基准复核。','{"source":"research_taxonomy_seed","requiredChecks":["合同基准","持仓行业暴露","风格暴露"]}'::jsonb,'2026-01-01'::date),
    ('000007.OF','peer-active-equity-sector-mid-3y','CSI_TECH','中证科技主题指数','sector_equity','peer_group_policy',0.82,'按主动权益行业主题策略族谱和科技成长风格映射；需在正式研究中复核主题指数代表性。','{"source":"research_taxonomy_seed","requiredChecks":["主题基准","行业暴露","重仓变化"]}'::jsonb,'2026-01-01'::date),
    ('000003.OF','peer-active-equity-core-mid-5y','CSI800','中证800','broad_equity','peer_group_policy',0.84,'按偏股混合核心均衡同类池映射；收益解释需拆权益配置和选股贡献。','{"source":"research_taxonomy_seed","requiredChecks":["权益仓位","风格暴露"]}'::jsonb,'2026-01-01'::date),
    ('000004.OF','peer-active-equity-sector-small-5y','CSI_SECTOR','行业主题指数','sector_equity','peer_group_policy',0.80,'按产业趋势主题同类池映射；正式研究需复核具体行业权重。','{"source":"research_taxonomy_seed","requiredChecks":["行业暴露","主题标签"]}'::jsonb,'2026-01-01'::date),
    ('000005.OF','peer-fixed-income-credit-mid-duration','CBA_CREDIT','中债信用债总财富指数','bond_credit','peer_group_policy',0.90,'按信用债中久期同类池映射；固收归因拆票息、资本利得和信用利差。','{"source":"research_taxonomy_seed","requiredChecks":["久期","评级分布","主体集中度"]}'::jsonb,'2026-01-01'::date),
    ('000006.OF','peer-fixed-income-credit-mid-duration','CBA_TOTAL','中债综合财富指数','bond_aggregate','peer_group_policy',0.86,'按稳健收益债券同类池映射；需区分久期收益与信用暴露。','{"source":"research_taxonomy_seed","requiredChecks":["久期","杠杆","评级分布"]}'::jsonb,'2026-01-01'::date),
    ('000008.OF','peer-index-hs300','000300.SH','沪深300','tracked_index','same_index_policy',0.96,'被动指数产品以跟踪指数为主基准；归因重点是跟踪差异、费用和现金拖累。','{"source":"research_taxonomy_seed","requiredChecks":["跟踪误差","费率","复制方式"]}'::jsonb,'2026-01-01'::date),
    ('000009.OF','peer-index-csi500','000905.SH','中证500','tracked_index','same_index_policy',0.96,'被动指数产品以跟踪指数为主基准；同指数优先横评。','{"source":"research_taxonomy_seed","requiredChecks":["跟踪误差","费率","复制方式"]}'::jsonb,'2026-01-01'::date),
    ('000010.OF','peer-money-cash-management','DR007','DR007','money_market_rate','cash_rate_policy',0.82,'货币基金以资金利率和同类收益中枢作研究参照；不做权益式超额能力解释。','{"source":"research_taxonomy_seed","requiredChecks":["流动性","剩余期限","收益中枢"]}'::jsonb,'2026-01-01'::date),
    ('000011.OF','peer-qdii-global-consumption','MSCI_GLOBAL_CONSUMER','MSCI全球消费','global_sector','peer_group_policy',0.83,'QDII 全球消费主题需拆区域市场收益和汇率贡献；基准映射来自全球消费主题同类池。','{"source":"research_taxonomy_seed","requiredChecks":["区域暴露","币种暴露","海外持仓"]}'::jsonb,'2026-01-01'::date),
    ('000012.OF','peer-active-equity-sector-small-5y','CSI_HEALTHCARE','中证医药卫生','sector_equity','peer_group_policy',0.84,'医药主题主动权益以行业主题指数解释 beta，再拆选股和行业内配置。','{"source":"research_taxonomy_seed","requiredChecks":["医药行业暴露","重仓变化"]}'::jsonb,'2026-01-01'::date),
    ('000013.OF','peer-fixed-income-credit-holding-period','CBA_INDUSTRIAL','中债产业债总财富指数','bond_credit','peer_group_policy',0.88,'产业债持有期产品按信用债持有期同类池映射；重点解释票息、利差和负债端稳定性。','{"source":"research_taxonomy_seed","requiredChecks":["持有期","评级分布","产业债暴露"]}'::jsonb,'2026-01-01'::date)
)
INSERT INTO benchmark_mappings (
  id, entity_id, peer_group_id, benchmark_code, benchmark_name,
  benchmark_type, mapping_method, confidence, rationale,
  evidence_refs, effective_from, effective_to, status, source, updated_at
)
SELECT
  'benchmark-mapping-' || mr.wind_code,
  fe.id,
  pg.id,
  mr.benchmark_code,
  mr.benchmark_name,
  mr.benchmark_type,
  mr.mapping_method,
  mr.confidence,
  mr.rationale,
  mr.evidence_refs,
  mr.effective_from,
  NULL,
  'active',
  'benchmark_attribution_seed',
  now()
FROM mapping_rows mr
JOIN fund_share_classes fsc ON fsc.wind_code = mr.wind_code
JOIN fund_entities fe ON fe.id = fsc.entity_id
JOIN peer_groups pg ON pg.key = mr.peer_group_key
ON CONFLICT (entity_id, benchmark_code, effective_from) DO UPDATE SET
  peer_group_id = EXCLUDED.peer_group_id,
  benchmark_name = EXCLUDED.benchmark_name,
  benchmark_type = EXCLUDED.benchmark_type,
  mapping_method = EXCLUDED.mapping_method,
  confidence = EXCLUDED.confidence,
  rationale = EXCLUDED.rationale,
  evidence_refs = EXCLUDED.evidence_refs,
  effective_to = EXCLUDED.effective_to,
  status = EXCLUDED.status,
  source = EXCLUDED.source,
  updated_at = now();

WITH attribution_rows(wind_code, benchmark_code, period_start, period_end, total_return, benchmark_return, allocation_effect, selection_effect, interaction_effect, style_contribution, industry_contribution, asset_allocation, residual_explanation, evidence_refs, quality_status) AS (
  VALUES
    ('000002.OF','CSI800','2025-06-01'::date,'2026-05-29'::date,0.1640,0.1020,0.0180,0.0370,0.0020,'[{"factor":"价值","contribution":0.012,"exposure":0.21},{"factor":"质量","contribution":0.009,"exposure":0.18}]'::jsonb,'[{"industry":"消费","contribution":0.014,"activeWeight":0.06},{"industry":"金融","contribution":-0.006,"activeWeight":-0.04}]'::jsonb,'[{"assetClass":"权益","weight":0.88,"contribution":0.151},{"assetClass":"现金","weight":0.04,"contribution":0.001}]'::jsonb,'残差约 0.0050，需用换手、交易成本和未覆盖行业继续解释，不能包装为能力。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29","researchDimensions":["基准映射","超额收益","配置效应","选择效应","风格","行业","资产配置","残差"]}'::jsonb,'reviewable'),
    ('000007.OF','CSI_TECH','2025-06-01'::date,'2026-05-29'::date,0.2100,0.1680,0.0090,0.0290,0.0010,'[{"factor":"成长","contribution":0.018,"exposure":0.35},{"factor":"动量","contribution":0.007,"exposure":0.16}]'::jsonb,'[{"industry":"电子","contribution":0.021,"activeWeight":0.09},{"industry":"计算机","contribution":0.011,"activeWeight":0.05}]'::jsonb,'[{"assetClass":"权益","weight":0.91,"contribution":0.196},{"assetClass":"现金","weight":0.03,"contribution":0.0005}]'::jsonb,'残差约 0.0030，需结合重仓变化和交易成本复核，不能包装为能力。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable'),
    ('000003.OF','CSI800','2025-06-01'::date,'2026-05-29'::date,0.0920,0.1020,-0.0060,-0.0020,0.0010,'[{"factor":"低波","contribution":0.006,"exposure":0.22},{"factor":"成长","contribution":-0.008,"exposure":-0.10}]'::jsonb,'[{"industry":"医药","contribution":-0.005,"activeWeight":0.03},{"industry":"公用事业","contribution":0.004,"activeWeight":0.04}]'::jsonb,'[{"assetClass":"权益","weight":0.72,"contribution":0.083},{"assetClass":"债券","weight":0.12,"contribution":0.005}]'::jsonb,'负超额主要来自风格和行业选择，残差需补交易成本。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable'),
    ('000005.OF','CBA_CREDIT','2025-06-01'::date,'2026-05-29'::date,0.0410,0.0320,0.0030,0.0040,0.0005,'[{"factor":"信用利差","contribution":0.003,"exposure":0.18},{"factor":"久期","contribution":0.002,"exposure":0.12}]'::jsonb,'[]'::jsonb,'[{"assetClass":"信用债","weight":0.76,"contribution":0.033},{"assetClass":"利率债","weight":0.12,"contribution":0.004}]'::jsonb,'残差约 0.0015，需补个券估值变动和杠杆成本。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable'),
    ('000008.OF','000300.SH','2025-06-01'::date,'2026-05-29'::date,0.1030,0.1070,-0.0010,-0.0020,0.0000,'[{"factor":"跟踪差异","contribution":-0.003,"exposure":1.0}]'::jsonb,'[{"industry":"指数成分","contribution":-0.002,"activeWeight":0.0}]'::jsonb,'[{"assetClass":"指数成分股","weight":0.95,"contribution":0.105},{"assetClass":"现金","weight":0.02,"contribution":-0.001}]'::jsonb,'负残差主要来自费用、现金拖累和采样/复制偏离。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable'),
    ('000011.OF','MSCI_GLOBAL_CONSUMER','2025-06-01'::date,'2026-05-29'::date,0.1150,0.0940,0.0070,0.0100,0.0010,'[{"factor":"美元汇率","contribution":0.006,"exposure":0.45},{"factor":"全球消费","contribution":0.009,"exposure":0.61}]'::jsonb,'[{"industry":"可选消费","contribution":0.013,"activeWeight":0.07},{"industry":"必选消费","contribution":-0.002,"activeWeight":-0.02}]'::jsonb,'[{"assetClass":"海外权益","weight":0.88,"contribution":0.104},{"assetClass":"现金","weight":0.05,"contribution":0.001}]'::jsonb,'残差约 0.0030，需补时区估值和汇兑处理明细。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable'),
    ('000013.OF','CBA_INDUSTRIAL','2025-06-01'::date,'2026-05-29'::date,0.0320,0.0290,0.0010,0.0015,0.0000,'[{"factor":"票息","contribution":0.002,"exposure":0.66},{"factor":"信用利差","contribution":0.0008,"exposure":0.24}]'::jsonb,'[]'::jsonb,'[{"assetClass":"产业债","weight":0.72,"contribution":0.027},{"assetClass":"现金","weight":0.06,"contribution":0.001}]'::jsonb,'残差约 0.0005，需补持有期负债端扰动解释。','{"source":"benchmark_attribution_seed","dataAsOf":"2026-05-29"}'::jsonb,'reviewable')
)
INSERT INTO attribution_explanations (
  id, entity_id, benchmark_mapping_id, period_start, period_end,
  total_return, benchmark_return, excess_return,
  allocation_effect, selection_effect, interaction_effect,
  style_contribution, industry_contribution, asset_allocation,
  residual_explanation, evidence_refs, quality_status, updated_at
)
SELECT
  'attribution-' || ar.wind_code || '-' || ar.period_end,
  fe.id,
  bm.id,
  ar.period_start,
  ar.period_end,
  ar.total_return,
  ar.benchmark_return,
  ar.total_return - ar.benchmark_return,
  ar.allocation_effect,
  ar.selection_effect,
  ar.interaction_effect,
  ar.style_contribution,
  ar.industry_contribution,
  ar.asset_allocation,
  ar.residual_explanation,
  ar.evidence_refs,
  ar.quality_status,
  now()
FROM attribution_rows ar
JOIN fund_share_classes fsc ON fsc.wind_code = ar.wind_code
JOIN fund_entities fe ON fe.id = fsc.entity_id
JOIN benchmark_mappings bm ON bm.entity_id = fe.id AND bm.benchmark_code = ar.benchmark_code
ON CONFLICT (entity_id, period_start, period_end, benchmark_mapping_id) DO UPDATE SET
  total_return = EXCLUDED.total_return,
  benchmark_return = EXCLUDED.benchmark_return,
  excess_return = EXCLUDED.excess_return,
  allocation_effect = EXCLUDED.allocation_effect,
  selection_effect = EXCLUDED.selection_effect,
  interaction_effect = EXCLUDED.interaction_effect,
  style_contribution = EXCLUDED.style_contribution,
  industry_contribution = EXCLUDED.industry_contribution,
  asset_allocation = EXCLUDED.asset_allocation,
  residual_explanation = EXCLUDED.residual_explanation,
  evidence_refs = EXCLUDED.evidence_refs,
  quality_status = EXCLUDED.quality_status,
  updated_at = now();
