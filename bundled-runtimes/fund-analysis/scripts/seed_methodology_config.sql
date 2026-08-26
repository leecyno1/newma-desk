CREATE TABLE IF NOT EXISTS research_methodology_templates (
  id text NOT NULL,
  key text NOT NULL,
  name text NOT NULL,
  fund_type text NOT NULL,
  asset_class text,
  active_passive text,
  description text,
  required_evidence jsonb NOT NULL,
  benchmark_policy jsonb,
  peer_policy jsonb,
  attribution_policy jsonb,
  holding_policy jsonb,
  manager_policy jsonb,
  company_policy jsonb,
  source text NOT NULL DEFAULT 'methodology_config',
  version text NOT NULL DEFAULT '1.0.0',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS research_methodology_templates_key_key
  ON research_methodology_templates (key);
CREATE INDEX IF NOT EXISTS research_methodology_templates_fund_type_idx
  ON research_methodology_templates (fund_type);
CREATE INDEX IF NOT EXISTS research_methodology_templates_asset_class_idx
  ON research_methodology_templates (asset_class);
CREATE INDEX IF NOT EXISTS research_methodology_templates_active_passive_idx
  ON research_methodology_templates (active_passive);
CREATE INDEX IF NOT EXISTS research_methodology_templates_is_active_idx
  ON research_methodology_templates (is_active);

CREATE TABLE IF NOT EXISTS research_methodology_dimensions (
  id text NOT NULL,
  template_id text NOT NULL,
  dimension_key text NOT NULL,
  name text NOT NULL,
  weight numeric(5,2),
  evidence_fields text[],
  calculation_policy jsonb,
  hard_gate boolean NOT NULL DEFAULT false,
  display_order integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS research_methodology_dimensions_template_id_dimension_key_key
  ON research_methodology_dimensions (template_id, dimension_key);
CREATE INDEX IF NOT EXISTS research_methodology_dimensions_template_id_idx
  ON research_methodology_dimensions (template_id);
CREATE INDEX IF NOT EXISTS research_methodology_dimensions_dimension_key_idx
  ON research_methodology_dimensions (dimension_key);
CREATE INDEX IF NOT EXISTS research_methodology_dimensions_hard_gate_idx
  ON research_methodology_dimensions (hard_gate);

CREATE TABLE IF NOT EXISTS research_methodology_mappings (
  id text NOT NULL,
  template_id text NOT NULL,
  strategy_family_id text,
  fund_type text,
  asset_class text,
  active_passive text,
  match_rules jsonb,
  priority integer NOT NULL DEFAULT 100,
  source text NOT NULL DEFAULT 'methodology_config',
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS research_methodology_mappings_template_id_idx
  ON research_methodology_mappings (template_id);
CREATE INDEX IF NOT EXISTS research_methodology_mappings_strategy_family_id_idx
  ON research_methodology_mappings (strategy_family_id);
CREATE INDEX IF NOT EXISTS research_methodology_mappings_fund_type_idx
  ON research_methodology_mappings (fund_type);
CREATE INDEX IF NOT EXISTS research_methodology_mappings_asset_class_idx
  ON research_methodology_mappings (asset_class);
CREATE INDEX IF NOT EXISTS research_methodology_mappings_active_passive_idx
  ON research_methodology_mappings (active_passive);
CREATE INDEX IF NOT EXISTS research_methodology_mappings_priority_idx
  ON research_methodology_mappings (priority);

INSERT INTO research_methodology_templates (
  id, key, name, fund_type, asset_class, active_passive, description,
  required_evidence, benchmark_policy, peer_policy, attribution_policy,
  holding_policy, manager_policy, company_policy, source, version, is_active, updated_at
) VALUES
  (
    'methodology-template-active-equity',
    'active_equity',
    '主动权益基金研究模板',
    'stock_hybrid',
    'equity',
    'active',
    '方法论模板只决定研究口径；主动权益重点解释超额收益、同类池、持仓穿透、经理任期和公司平台，不输出交易执行或组合动作。',
    '["benchmark_mapping","excess_return","style_exposure","industry_attribution","peer_group_policy","top_holdings","concentration","tenure_slice","representative_fund"]'::jsonb,
    '{"primary":"风格适配基准","checks":["超额收益","风格暴露","行业归因"]}'::jsonb,
    '{"layers":["资产类别","主动/被动","风格","规模","成立年限"],"explainable":true}'::jsonb,
    '{"sources":["配置","选股","风格","残差"],"frequency":"quarterly"}'::jsonb,
    '{"focus":["行业暴露","主题标签","集中度","换手","重仓变化"]}'::jsonb,
    '{"focus":["任期切片","代表作归因","风格漂移","团队贡献"]}'::jsonb,
    '{"focus":["产品线","投研团队","平台能力","同公司横评"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-fixed-income',
    'fixed_income',
    '固收基金研究模板',
    'bond',
    'fixed_income',
    'active',
    '方法论模板只决定研究口径；固收重点解释信用暴露、久期曲线、票息/资本利得/利差来源和平台信用研究能力。',
    '["rating_distribution","issuer_concentration","default_history","duration","yield_curve_exposure","leverage","bond_benchmark","carry_return","capital_gain","bond_type","duration_bucket","credit_bucket"]'::jsonb,
    '{"primary":"中债类财富指数","checks":["久期匹配","信用等级","杠杆口径"]}'::jsonb,
    '{"layers":["债券类型","久期桶","信用桶","杠杆水平","持有期结构"],"explainable":true}'::jsonb,
    '{"sources":["票息","资本利得","信用利差","杠杆"],"frequency":"monthly"}'::jsonb,
    '{"focus":["评级分布","主体集中度","券种结构","杠杆"]}'::jsonb,
    '{"focus":["任期切片","回撤控制","信用事件处理"]}'::jsonb,
    '{"focus":["固收团队","信用研究平台","交易支持"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-index-fund',
    'index_fund',
    '指数基金研究模板',
    'index',
    'index',
    'passive',
    '方法论模板只决定研究口径；指数基金重点验证跟踪标的、复制方式、费用、偏离、规模流动性和同指数横评。',
    '["expense_ratio","tracking_error","tracking_difference","index_benchmark","replication_method","aum","turnover","creation_redemption","same_index_peers","share_class"]'::jsonb,
    '{"primary":"跟踪指数","checks":["复制方式","跟踪偏离","费用拖累"]}'::jsonb,
    '{"layers":["同指数","份额类型","规模","费率","流动性"],"explainable":true}'::jsonb,
    '{"sources":["指数收益","跟踪差异","现金拖累","费用"],"frequency":"monthly"}'::jsonb,
    '{"focus":["成分券","权重偏离","现金比例"]}'::jsonb,
    '{"focus":["运营负责人","指数产品经验"]}'::jsonb,
    '{"focus":["指数产品线","运营能力","做市与申赎支持"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-money-market',
    'money_market',
    '货币基金研究模板',
    'money',
    'money_market',
    'active',
    '方法论模板只决定研究口径；货币基金重点评价收益中枢、本金保护、收益稳定性、规模流动性和数据时点，不输出交易执行或组合动作。',
    '["seven_day_annualized_yield","annualized_return","max_drawdown","annualized_volatility","positive_return_ratio","aum","source_freshness","peer_group_policy"]'::jsonb,
    '{"primary":"资金利率与货币基金收益中枢","checks":["七日年化收益率","收益稳定性","流动性"]}'::jsonb,
    '{"layers":["货币基金","份额类型","规模","流动性"],"explainable":true}'::jsonb,
    '{"sources":["票息与再投资收益","费用","流动性管理"],"frequency":"weekly"}'::jsonb,
    '{"focus":["剩余期限","高流动性资产","信用等级"]}'::jsonb,
    '{"focus":["流动性管理经验","信用事件处理"]}'::jsonb,
    '{"focus":["现金管理产品线","流动性支持","信用研究平台"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-qdii',
    'qdii',
    'QDII 基金研究模板',
    'qdii',
    'global',
    null,
    '方法论模板只决定研究口径；QDII 重点拆分区域市场、币种、海外持仓、汇率贡献、额度和海外平台能力。',
    '["region_exposure","currency_exposure","fx_policy","global_benchmark","local_market_return","fx_return","overseas_holdings","sector_exposure","country_exposure","region_bucket","asset_class","active_passive"]'::jsonb,
    '{"primary":"区域/主题适配海外指数","checks":["本地市场收益","汇率贡献","时区与估值口径"]}'::jsonb,
    '{"layers":["区域","币种","资产类别","主被动","主题"],"explainable":true}'::jsonb,
    '{"sources":["区域市场","汇率","主动贡献","费用"],"frequency":"monthly"}'::jsonb,
    '{"focus":["海外持仓","国家暴露","行业暴露","币种暴露"]}'::jsonb,
    '{"focus":["海外任期","顾问角色","团队分工"]}'::jsonb,
    '{"focus":["QDII 额度","海外投研平台","运营能力"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-fof',
    'fof',
    'FOF 基金研究模板',
    'fof',
    'multi_asset',
    'active',
    '方法论模板只决定研究口径；FOF 重点穿透底层基金、资产配置归因、双层费用、风险目标和基金筛选能力。',
    '["underlying_funds","lookthrough_asset_allocation","double_fee","allocation_policy","rebalance_history","allocation_effect","risk_target","equity_center","holding_period"]'::jsonb,
    '{"primary":"风险目标适配基准","checks":["权益中枢","再平衡","底层基金贡献"]}'::jsonb,
    '{"layers":["风险目标","权益中枢","持有期","底层基金类型"],"explainable":true}'::jsonb,
    '{"sources":["资产配置","基金选择","再平衡","费用"],"frequency":"quarterly"}'::jsonb,
    '{"focus":["底层基金","资产穿透","重叠持仓","双层费率"]}'::jsonb,
    '{"focus":["FOF 任期","基金筛选记录","配置纪律"]}'::jsonb,
    '{"focus":["FOF 团队","基金研究平台","产品准入能力"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  ),
  (
    'methodology-template-quant-fund',
    'quant_fund',
    '量化基金研究模板',
    'quant',
    'equity_quant',
    'active',
    '方法论模板只决定研究口径；量化基金重点验证模型稳定性、因子衰减、容量信号、归因、换手和量化平台能力。',
    '["factor_decay","ic_stability","capacity_signal","benchmark_mapping","factor_attribution","residual_return","holding_count","industry_neutrality","turnover","strategy_type","benchmark_index","hedging_policy"]'::jsonb,
    '{"primary":"策略适配指数","checks":["因子归因","行业中性","残差收益"]}'::jsonb,
    '{"layers":["策略类型","基准指数","对冲政策","容量","换手"],"explainable":true}'::jsonb,
    '{"sources":["因子","行业","风格","残差","交易成本"],"frequency":"monthly"}'::jsonb,
    '{"focus":["持仓数量","行业中性","换手","容量"]}'::jsonb,
    '{"focus":["模型负责人","团队变更","研究生产链"]}'::jsonb,
    '{"focus":["量化平台","数据工程","投研系统"]}'::jsonb,
    'methodology_seed',
    '1.0.0',
    true,
    now()
  )
ON CONFLICT (key) DO UPDATE SET
  name = EXCLUDED.name,
  fund_type = EXCLUDED.fund_type,
  asset_class = EXCLUDED.asset_class,
  active_passive = EXCLUDED.active_passive,
  description = EXCLUDED.description,
  required_evidence = EXCLUDED.required_evidence,
  benchmark_policy = EXCLUDED.benchmark_policy,
  peer_policy = EXCLUDED.peer_policy,
  attribution_policy = EXCLUDED.attribution_policy,
  holding_policy = EXCLUDED.holding_policy,
  manager_policy = EXCLUDED.manager_policy,
  company_policy = EXCLUDED.company_policy,
  source = EXCLUDED.source,
  version = EXCLUDED.version,
  is_active = EXCLUDED.is_active,
  updated_at = now();

WITH dimension_rows(template_key, id, dimension_key, name, weight, evidence_fields, calculation_policy, hard_gate, display_order) AS (
  VALUES
    ('active_equity','methodology-dimension-active-equity-benchmark','benchmark_attribution','基准与归因',22.00,ARRAY['benchmark_mapping','excess_return','style_exposure','industry_attribution'],'{"reason":"主动权益必须解释超额收益来自配置、选股、风格还是残差。"}'::jsonb,true,10),
    ('active_equity','methodology-dimension-active-equity-peer','peer_group','同类池',16.00,ARRAY['peer_group_policy','asset_class','style_tags','scale_bucket'],'{"reason":"同类池决定排名和分位是否可解释。"}'::jsonb,true,20),
    ('active_equity','methodology-dimension-active-equity-holding','holding_lookthrough','持仓穿透',18.00,ARRAY['top_holdings','industry_exposure','concentration','turnover'],'{"reason":"主动权益研究要看行业、主题、集中度和重仓变化。"}'::jsonb,true,30),
    ('active_equity','methodology-dimension-active-equity-manager','manager','基金经理',22.00,ARRAY['tenure_slice','representative_fund','style_drift'],'{"reason":"经理任期和代表作是主动权益能力识别核心。"}'::jsonb,true,40),
    ('active_equity','methodology-dimension-active-equity-company','company','基金公司',12.00,ARRAY['product_line','research_team','platform_capability'],'{"reason":"公司平台用于解释能力可复制性。"}'::jsonb,false,50),
    ('active_equity','methodology-dimension-active-equity-fee','fee_tracking','费用与跟踪误差',10.00,ARRAY['fee_rate','tracking_error'],'{"reason":"费用和波动拖累影响长期研究结论稳定性。"}'::jsonb,false,60),

    ('fixed_income','methodology-dimension-fixed-income-credit','credit_exposure','信用暴露',24.00,ARRAY['rating_distribution','issuer_concentration','default_history'],'{"reason":"固收收益不能脱离信用下沉和主体集中度解释。"}'::jsonb,true,10),
    ('fixed_income','methodology-dimension-fixed-income-duration','duration_curve','久期与曲线暴露',18.00,ARRAY['duration','yield_curve_exposure','leverage'],'{"reason":"久期、杠杆和曲线位置决定利率风险来源。"}'::jsonb,true,20),
    ('fixed_income','methodology-dimension-fixed-income-benchmark','benchmark_attribution','基准与归因',16.00,ARRAY['bond_benchmark','carry_return','capital_gain'],'{"reason":"固收归因要拆票息、资本利得和信用利差。"}'::jsonb,true,30),
    ('fixed_income','methodology-dimension-fixed-income-peer','peer_group','同类池',14.00,ARRAY['bond_type','duration_bucket','credit_bucket'],'{"reason":"纯债、短债、二级债不可混池比较。"}'::jsonb,true,40),
    ('fixed_income','methodology-dimension-fixed-income-manager','manager','基金经理',14.00,ARRAY['tenure_slice','drawdown_control'],'{"reason":"经理研究侧重回撤控制和信用风险处理。"}'::jsonb,false,50),
    ('fixed_income','methodology-dimension-fixed-income-company','company','基金公司',14.00,ARRAY['fixed_income_team','credit_research_platform'],'{"reason":"固收更依赖平台信用研究和交易支持能力。"}'::jsonb,false,60),

    ('index_fund','methodology-dimension-index-fee','fee_tracking','费用与跟踪误差',28.00,ARRAY['expense_ratio','tracking_error','tracking_difference'],'{"reason":"指数基金核心是低成本和低偏离。"}'::jsonb,true,10),
    ('index_fund','methodology-dimension-index-benchmark','benchmark_attribution','基准与归因',22.00,ARRAY['index_benchmark','replication_method','tracking_difference'],'{"reason":"必须确认跟踪标的、复制方式和偏离来源。"}'::jsonb,true,20),
    ('index_fund','methodology-dimension-index-liquidity','liquidity_scale','规模与流动性',18.00,ARRAY['aum','turnover','creation_redemption'],'{"reason":"规模和流动性影响指数产品可持续性和偏离。"}'::jsonb,true,30),
    ('index_fund','methodology-dimension-index-holding','holding_lookthrough','持仓穿透',14.00,ARRAY['constituents','weight_deviation'],'{"reason":"持仓用于验证是否贴合指数。"}'::jsonb,false,40),
    ('index_fund','methodology-dimension-index-peer','peer_group','同类池',10.00,ARRAY['same_index_peers','share_class'],'{"reason":"指数产品优先同指数横评。"}'::jsonb,true,50),
    ('index_fund','methodology-dimension-index-company','company','基金公司',8.00,ARRAY['index_product_line','operations_capability'],'{"reason":"被动产品更关注运营和产品线能力。"}'::jsonb,false,60),

    ('money_market','methodology-dimension-money-income','income_competitiveness','收益竞争力',35.00,ARRAY['seven_day_annualized_yield','annualized_return'],'{"reason":"货币基金需同时观察七日年化收益率和较长窗口收益中枢。"}'::jsonb,true,10),
    ('money_market','methodology-dimension-money-preservation','capital_preservation','本金保护',30.00,ARRAY['max_drawdown'],'{"reason":"净值回撤是货币基金稳定性评价的硬证据。"}'::jsonb,true,20),
    ('money_market','methodology-dimension-money-stability','income_stability','收益稳定性',15.00,ARRAY['annualized_volatility','positive_return_ratio'],'{"reason":"波动和正收益比例用于识别收益中枢是否稳定。"}'::jsonb,false,30),
    ('money_market','methodology-dimension-money-liquidity','liquidity_scale','规模与流动性',10.00,ARRAY['aum'],'{"reason":"规模是流动性管理和赎回承接能力的代理证据。"}'::jsonb,true,40),
    ('money_market','methodology-dimension-money-quality','data_quality','数据质量',10.00,ARRAY['source_freshness'],'{"reason":"短周期收益指标必须保留来源与时点。"}'::jsonb,false,50),

    ('qdii','methodology-dimension-qdii-region-currency','region_currency','汇率与区域暴露',22.00,ARRAY['region_exposure','currency_exposure','fx_policy'],'{"reason":"QDII 必须把区域市场和汇率暴露拆开。"}'::jsonb,true,10),
    ('qdii','methodology-dimension-qdii-benchmark','benchmark_attribution','基准与归因',18.00,ARRAY['global_benchmark','local_market_return','fx_return'],'{"reason":"海外基金超额要区分市场、汇率和主动贡献。"}'::jsonb,true,20),
    ('qdii','methodology-dimension-qdii-holding','holding_lookthrough','持仓穿透',18.00,ARRAY['overseas_holdings','sector_exposure','country_exposure'],'{"reason":"海外持仓穿透决定主题和区域风险解释。"}'::jsonb,true,30),
    ('qdii','methodology-dimension-qdii-peer','peer_group','同类池',14.00,ARRAY['region_bucket','asset_class','active_passive'],'{"reason":"不同市场和币种不可简单横评。"}'::jsonb,true,40),
    ('qdii','methodology-dimension-qdii-manager','manager','基金经理',14.00,ARRAY['overseas_tenure','advisor_role'],'{"reason":"需区分境内经理、海外顾问和团队贡献。"}'::jsonb,false,50),
    ('qdii','methodology-dimension-qdii-company','company','基金公司',14.00,ARRAY['qdii_quota','overseas_platform'],'{"reason":"QDII 研究要看海外投研和额度/运营能力。"}'::jsonb,false,60),

    ('fof','methodology-dimension-fof-underlying','underlying_lookthrough','底层基金穿透',28.00,ARRAY['underlying_funds','lookthrough_asset_allocation','double_fee'],'{"reason":"FOF 首先要穿透到底层基金和资产配置。"}'::jsonb,true,10),
    ('fof','methodology-dimension-fof-allocation','asset_allocation','资产配置归因',20.00,ARRAY['allocation_policy','rebalance_history','allocation_effect'],'{"reason":"FOF 收益主要来自资产配置和基金选择。"}'::jsonb,true,20),
    ('fof','methodology-dimension-fof-peer','peer_group','同类池',14.00,ARRAY['risk_target','equity_center','holding_period'],'{"reason":"FOF 要按风险目标和权益中枢构建同类池。"}'::jsonb,true,30),
    ('fof','methodology-dimension-fof-manager','manager','基金经理',16.00,ARRAY['fof_tenure','fund_selection_record'],'{"reason":"经理评价侧重资产配置纪律和基金筛选能力。"}'::jsonb,false,40),
    ('fof','methodology-dimension-fof-company','company','基金公司',12.00,ARRAY['fof_team','fund_research_platform'],'{"reason":"FOF 更依赖基金研究平台和产品准入能力。"}'::jsonb,false,50),
    ('fof','methodology-dimension-fof-fee','fee_tracking','费用与跟踪误差',10.00,ARRAY['management_fee','underlying_fee'],'{"reason":"双重费率会侵蚀长期收益解释。"}'::jsonb,false,60),

    ('quant_fund','methodology-dimension-quant-model','model_stability','模型稳定性',24.00,ARRAY['factor_decay','ic_stability','capacity_signal'],'{"reason":"量化基金必须验证模型有效性、衰减和容量约束。"}'::jsonb,true,10),
    ('quant_fund','methodology-dimension-quant-benchmark','benchmark_attribution','基准与归因',20.00,ARRAY['benchmark_mapping','factor_attribution','residual_return'],'{"reason":"指数增强和量化策略要拆因子、行业和残差。"}'::jsonb,true,20),
    ('quant_fund','methodology-dimension-quant-holding','holding_lookthrough','持仓穿透',16.00,ARRAY['holding_count','industry_neutrality','turnover'],'{"reason":"持仓数量、换手和中性约束影响收益稳定性。"}'::jsonb,true,30),
    ('quant_fund','methodology-dimension-quant-peer','peer_group','同类池',14.00,ARRAY['strategy_type','benchmark_index','hedging_policy'],'{"reason":"量化多头、指数增强、市场中性不能混池。"}'::jsonb,true,40),
    ('quant_fund','methodology-dimension-quant-manager','manager','基金经理',12.00,ARRAY['team_change','model_owner'],'{"reason":"需识别模型团队而非只看挂名经理。"}'::jsonb,false,50),
    ('quant_fund','methodology-dimension-quant-company','company','基金公司',14.00,ARRAY['quant_platform','data_infrastructure'],'{"reason":"量化能力依赖数据、工程和研究平台。"}'::jsonb,false,60)
)
INSERT INTO research_methodology_dimensions (
  id, template_id, dimension_key, name, weight, evidence_fields,
  calculation_policy, hard_gate, display_order, updated_at
)
SELECT
  d.id,
  t.id,
  d.dimension_key,
  d.name,
  d.weight,
  d.evidence_fields,
  d.calculation_policy,
  d.hard_gate,
  d.display_order,
  now()
FROM dimension_rows d
JOIN research_methodology_templates t ON t.key = d.template_key
ON CONFLICT (template_id, dimension_key) DO UPDATE SET
  name = EXCLUDED.name,
  weight = EXCLUDED.weight,
  evidence_fields = EXCLUDED.evidence_fields,
  calculation_policy = EXCLUDED.calculation_policy,
  hard_gate = EXCLUDED.hard_gate,
  display_order = EXCLUDED.display_order,
  updated_at = now();

WITH mapping_rows(template_key, id, fund_type, asset_class, active_passive, match_rules, priority) AS (
  VALUES
    ('active_equity','methodology-mapping-active-equity-stock','stock','equity','active','{"aliases":["主动权益","权益","股票型","混合型","偏股混合","active_equity"],"strategyFamilies":["value","growth","quality","sector"]}'::jsonb,10),
    ('active_equity','methodology-mapping-active-equity-hybrid','hybrid','equity','active','{"aliases":["混合","偏股","灵活配置","平衡混合"],"styleRequired":true}'::jsonb,20),
    ('fixed_income','methodology-mapping-fixed-income-bond','bond','fixed_income','active','{"aliases":["固收","债券","纯债","短债","二级债","fixed_income"],"riskBuckets":["duration","credit"]}'::jsonb,10),
    ('index_fund','methodology-mapping-index-fund-index','index','index','passive','{"aliases":["指数","ETF","被动","联接","index_fund"],"sameIndexFirst":true}'::jsonb,10),
    ('money_market','methodology-mapping-money-market-money','money','money_market','active','{"aliases":["货币","现金管理","money_market"],"liquidityEvidenceRequired":true}'::jsonb,10),
    ('qdii','methodology-mapping-qdii-global','qdii','global',null,'{"aliases":["QDII","海外","全球","港股","美股","区域"],"requiresCurrencyExposure":true}'::jsonb,10),
    ('fof','methodology-mapping-fof-multi-asset','fof','multi_asset','active','{"aliases":["FOF","基金中基金","养老","目标日期","目标风险"],"requiresUnderlyingFunds":true}'::jsonb,10),
    ('quant_fund','methodology-mapping-quant-equity','quant','equity_quant','active','{"aliases":["量化","指数增强","市场中性","多因子","quant_fund"],"requiresModelEvidence":true}'::jsonb,10),
    ('quant_fund','methodology-mapping-quant-enhanced-index','index_enhanced','equity_quant','active','{"aliases":["指数增强","增强指数","量化增强"],"benchmarkIndexRequired":true}'::jsonb,20)
)
INSERT INTO research_methodology_mappings (
  id, template_id, fund_type, asset_class, active_passive,
  match_rules, priority, source, updated_at
)
SELECT
  m.id,
  t.id,
  m.fund_type,
  m.asset_class,
  m.active_passive,
  m.match_rules,
  m.priority,
  'methodology_seed',
  now()
FROM mapping_rows m
JOIN research_methodology_templates t ON t.key = m.template_key
ON CONFLICT (id) DO UPDATE SET
  template_id = EXCLUDED.template_id,
  fund_type = EXCLUDED.fund_type,
  asset_class = EXCLUDED.asset_class,
  active_passive = EXCLUDED.active_passive,
  match_rules = EXCLUDED.match_rules,
  priority = EXCLUDED.priority,
  source = EXCLUDED.source,
  updated_at = now();
