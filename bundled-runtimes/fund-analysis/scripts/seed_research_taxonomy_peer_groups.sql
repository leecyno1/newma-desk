CREATE TABLE IF NOT EXISTS strategy_families (
  id text NOT NULL,
  key text NOT NULL,
  name text NOT NULL,
  asset_class text,
  active_passive text,
  style_tags text[],
  benchmark_policy jsonb,
  peer_policy jsonb,
  source text NOT NULL DEFAULT 'methodology_config',
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS strategy_families_key_key ON strategy_families (key);
CREATE INDEX IF NOT EXISTS strategy_families_asset_class_idx ON strategy_families (asset_class);
CREATE INDEX IF NOT EXISTS strategy_families_active_passive_idx ON strategy_families (active_passive);

CREATE TABLE IF NOT EXISTS fund_entities (
  id text NOT NULL,
  canonical_code text NOT NULL,
  canonical_name text NOT NULL,
  normalized_name text NOT NULL,
  company_id text,
  product_line_id text,
  strategy_family_id text,
  asset_class text,
  active_passive text,
  lifecycle_stage text NOT NULL DEFAULT 'active',
  established_at date,
  terminated_at date,
  source text NOT NULL DEFAULT 'entity_standardization',
  source_updated_at date,
  raw_data jsonb,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS fund_entities_canonical_code_key ON fund_entities (canonical_code);
CREATE INDEX IF NOT EXISTS fund_entities_normalized_name_idx ON fund_entities (normalized_name);
CREATE INDEX IF NOT EXISTS fund_entities_strategy_family_id_idx ON fund_entities (strategy_family_id);
CREATE INDEX IF NOT EXISTS fund_entities_asset_class_idx ON fund_entities (asset_class);
CREATE INDEX IF NOT EXISTS fund_entities_lifecycle_stage_idx ON fund_entities (lifecycle_stage);

CREATE TABLE IF NOT EXISTS fund_share_classes (
  id text NOT NULL,
  entity_id text NOT NULL,
  fund_id text,
  wind_code text NOT NULL,
  share_class text,
  fee_class text,
  currency text DEFAULT 'CNY',
  is_primary boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active',
  source text NOT NULL DEFAULT 'share_class_normalizer',
  source_updated_at date,
  raw_data jsonb,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS fund_share_classes_wind_code_key ON fund_share_classes (wind_code);
CREATE INDEX IF NOT EXISTS fund_share_classes_entity_id_idx ON fund_share_classes (entity_id);
CREATE INDEX IF NOT EXISTS fund_share_classes_fund_id_idx ON fund_share_classes (fund_id);
CREATE INDEX IF NOT EXISTS fund_share_classes_share_class_idx ON fund_share_classes (share_class);
CREATE INDEX IF NOT EXISTS fund_share_classes_status_idx ON fund_share_classes (status);

CREATE TABLE IF NOT EXISTS peer_groups (
  id text NOT NULL,
  key text NOT NULL,
  name text NOT NULL,
  strategy_family_id text,
  asset_class text NOT NULL,
  active_passive text NOT NULL,
  benchmark_code text,
  benchmark_name text,
  inclusion_rules jsonb NOT NULL,
  exclusion_rules jsonb,
  minimum_peer_count integer NOT NULL DEFAULT 10,
  source text NOT NULL DEFAULT 'peer_group_policy',
  source_updated_at date,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS peer_groups_key_key ON peer_groups (key);
CREATE INDEX IF NOT EXISTS peer_groups_strategy_family_id_idx ON peer_groups (strategy_family_id);
CREATE INDEX IF NOT EXISTS peer_groups_asset_class_idx ON peer_groups (asset_class);
CREATE INDEX IF NOT EXISTS peer_groups_active_passive_idx ON peer_groups (active_passive);
CREATE INDEX IF NOT EXISTS peer_groups_benchmark_code_idx ON peer_groups (benchmark_code);

CREATE TABLE IF NOT EXISTS peer_group_members (
  id text NOT NULL,
  peer_group_id text NOT NULL,
  entity_id text NOT NULL,
  role text NOT NULL DEFAULT 'member',
  matched_rules jsonb NOT NULL,
  excluded_rules jsonb,
  sample_as_of_date date,
  confidence numeric(5,2),
  source text NOT NULL DEFAULT 'peer_group_builder',
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS peer_group_members_peer_group_id_entity_id_key
  ON peer_group_members (peer_group_id, entity_id);
CREATE INDEX IF NOT EXISTS peer_group_members_peer_group_id_idx ON peer_group_members (peer_group_id);
CREATE INDEX IF NOT EXISTS peer_group_members_entity_id_idx ON peer_group_members (entity_id);
CREATE INDEX IF NOT EXISTS peer_group_members_role_idx ON peer_group_members (role);

INSERT INTO strategy_families (
  id, key, name, asset_class, active_passive, style_tags,
  benchmark_policy, peer_policy, source, updated_at
) VALUES
  (
    'strategy-family-active-equity-core',
    'active_equity_core',
    '主动权益-核心/均衡',
    'equity',
    'active',
    ARRAY['主动权益','核心','均衡','价值成长'],
    '{"defaultBenchmarks":["沪深300","中证800","偏股混合基金指数"],"mappingRationale":"按权益仓位、风格暴露和合同基准确认主基准。"}'::jsonb,
    '{"requiredLayers":["资产类别","策略族谱","主动/被动","风格","规模","成立年限"],"minimumPeerCount":5,"exclusionRules":["被动指数","货币","纯债","QDII"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  ),
  (
    'strategy-family-active-equity-sector',
    'active_equity_sector',
    '主动权益-行业/主题',
    'equity',
    'active',
    ARRAY['主动权益','行业主题','医药','科技','高集中度'],
    '{"defaultBenchmarks":["中证行业指数","主题指数","中证800"],"mappingRationale":"主题基金必须优先匹配行业/主题基准，再披露宽基差异。"}'::jsonb,
    '{"requiredLayers":["资产类别","主题标签","主动/被动","行业暴露","规模","成立年限"],"minimumPeerCount":5,"exclusionRules":["宽基指数","纯债","货币"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  ),
  (
    'strategy-family-fixed-income-credit',
    'fixed_income_credit',
    '固收-信用债/产业债',
    'fixed_income',
    'active',
    ARRAY['固收','信用债','产业债','票息'],
    '{"defaultBenchmarks":["中债综合财富指数","中债信用债总财富指数","中债产业债总财富指数"],"mappingRationale":"按券种、久期和信用等级确认债券基准。"}'::jsonb,
    '{"requiredLayers":["债券类型","久期桶","信用桶","杠杆水平","持有期"],"minimumPeerCount":5,"exclusionRules":["权益基金","货币","QDII"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  ),
  (
    'strategy-family-index-broad',
    'index_broad',
    '指数-宽基',
    'index',
    'passive',
    ARRAY['指数','宽基','被动','ETF联接'],
    '{"defaultBenchmarks":["沪深300","中证500","指数全收益"],"mappingRationale":"指数基金以跟踪指数为唯一主基准，同指数优先横评。"}'::jsonb,
    '{"requiredLayers":["同指数","份额类型","规模","费率","流动性"],"minimumPeerCount":5,"exclusionRules":["主动权益","增强指数","非同指数"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  ),
  (
    'strategy-family-qdii-global-theme',
    'qdii_global_theme',
    'QDII-全球/区域主题',
    'global',
    'active',
    ARRAY['QDII','全球','区域','汇率','海外主题'],
    '{"defaultBenchmarks":["MSCI全球指数","区域主题指数","标普全球行业指数"],"mappingRationale":"海外基金需拆区域市场收益和汇率贡献。"}'::jsonb,
    '{"requiredLayers":["区域","币种","资产类别","主被动","主题"],"minimumPeerCount":5,"exclusionRules":["境内权益","境内债券","货币"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  ),
  (
    'strategy-family-cash-management',
    'cash_management',
    '货币-现金管理',
    'money_market',
    'active',
    ARRAY['货币','现金管理','流动性'],
    '{"defaultBenchmarks":["DR007","货币基金收益率中枢"],"mappingRationale":"货币基金以资金利率和同类收益中枢作为研究参照。"}'::jsonb,
    '{"requiredLayers":["货币基金","流动性","剩余期限","规模"],"minimumPeerCount":5,"exclusionRules":["权益","债券增强","QDII"]}'::jsonb,
    'research_taxonomy_seed',
    now()
  )
ON CONFLICT (key) DO UPDATE SET
  name = EXCLUDED.name,
  asset_class = EXCLUDED.asset_class,
  active_passive = EXCLUDED.active_passive,
  style_tags = EXCLUDED.style_tags,
  benchmark_policy = EXCLUDED.benchmark_policy,
  peer_policy = EXCLUDED.peer_policy,
  source = EXCLUDED.source,
  updated_at = now();

WITH fund_rows(canonical_code, canonical_name, normalized_name, strategy_family_key, asset_class, active_passive, established_at, wind_code, fund_id, style_tags, scale_bucket, peer_group_key) AS (
  VALUES
    ('entity-000002','易方达均衡价值股票','易方达均衡价值股票','active_equity_core','equity','active','2015-06-12'::date,'000002.OF','ac546c3f-6b2b-4017-8fe3-21b74dc5bf77',ARRAY['均衡价值','核心'], 'large', 'peer-active-equity-core-large-5y'),
    ('entity-000007','富国科技成长股票','富国科技成长股票','active_equity_sector','equity','active','2020-07-17'::date,'000007.OF','138e20c8-a626-4fae-b24b-96f37c75033a',ARRAY['科技成长','高波动'], 'mid', 'peer-active-equity-sector-mid-3y'),
    ('entity-000003','广发稳健增长混合','广发稳健增长混合','active_equity_core','equity','active','2018-03-21'::date,'000003.OF',NULL,ARRAY['稳健成长','偏股混合'], 'mid', 'peer-active-equity-core-mid-5y'),
    ('entity-000004','南方产业趋势混合','南方产业趋势混合','active_equity_sector','equity','active','2019-11-08'::date,'000004.OF',NULL,ARRAY['产业趋势','行业主题'], 'small', 'peer-active-equity-sector-small-5y'),
    ('entity-000005','博时信用优选债券','博时信用优选债券','fixed_income_credit','fixed_income','active','2016-09-23'::date,'000005.OF',NULL,ARRAY['信用债','中长期'], 'mid', 'peer-fixed-income-credit-mid-duration'),
    ('entity-000006','招商安心收益债券','招商安心收益债券','fixed_income_credit','fixed_income','active','2014-04-18'::date,'000006.OF',NULL,ARRAY['利率债','稳健收益'], 'small', 'peer-fixed-income-credit-mid-duration'),
    ('entity-000008','华夏沪深300指数','华夏沪深300指数','index_broad','index','passive','2012-05-04'::date,'000008.OF',NULL,ARRAY['沪深300','宽基'], 'large', 'peer-index-hs300'),
    ('entity-000009','嘉实中证500指数','嘉实中证500指数','index_broad','index','passive','2017-01-11'::date,'000009.OF',NULL,ARRAY['中证500','宽基'], 'mid', 'peer-index-csi500'),
    ('entity-000010','天弘现金管家货币','天弘现金管家货币','cash_management','money_market','active','2013-08-15'::date,'000010.OF',NULL,ARRAY['现金管理','流动性'], 'large', 'peer-money-cash-management'),
    ('entity-000011','汇添富全球消费QDII','汇添富全球消费QDII','qdii_global_theme','global','active','2021-02-05'::date,'000011.OF',NULL,ARRAY['全球消费','QDII'], 'small', 'peer-qdii-global-consumption'),
    ('entity-000012','工银瑞信医疗创新股票','工银瑞信医疗创新股票','active_equity_sector','equity','active','2019-06-28'::date,'000012.OF',NULL,ARRAY['医药成长','行业主题'], 'small', 'peer-active-equity-sector-small-5y'),
    ('entity-000013','鹏华产业债一年持有','鹏华产业债一年持有','fixed_income_credit','fixed_income','active','2022-10-14'::date,'000013.OF',NULL,ARRAY['产业债','持有期'], 'small', 'peer-fixed-income-credit-holding-period')
)
INSERT INTO fund_entities (
  id, canonical_code, canonical_name, normalized_name, strategy_family_id,
  asset_class, active_passive, lifecycle_stage, established_at,
  source, source_updated_at, raw_data, updated_at
)
SELECT
  fr.canonical_code,
  fr.canonical_code,
  fr.canonical_name,
  fr.normalized_name,
  sf.id,
  fr.asset_class,
  fr.active_passive,
  'active',
  fr.established_at,
  'research_taxonomy_seed',
  '2026-06-14'::date,
  jsonb_build_object('researchObject', '基金实体', 'researchBoundary', '策略族谱与同类池只服务基金研究比较', 'styleTags', fr.style_tags, 'scaleBucket', fr.scale_bucket, 'peerGroupKey', fr.peer_group_key),
  now()
FROM fund_rows fr
JOIN strategy_families sf ON sf.key = fr.strategy_family_key
ON CONFLICT (canonical_code) DO UPDATE SET
  canonical_name = EXCLUDED.canonical_name,
  normalized_name = EXCLUDED.normalized_name,
  strategy_family_id = EXCLUDED.strategy_family_id,
  asset_class = EXCLUDED.asset_class,
  active_passive = EXCLUDED.active_passive,
  lifecycle_stage = EXCLUDED.lifecycle_stage,
  established_at = EXCLUDED.established_at,
  source = EXCLUDED.source,
  source_updated_at = EXCLUDED.source_updated_at,
  raw_data = EXCLUDED.raw_data,
  updated_at = now();

WITH fund_rows(canonical_code, wind_code, fund_id) AS (
  VALUES
    ('entity-000002','000002.OF','ac546c3f-6b2b-4017-8fe3-21b74dc5bf77'),
    ('entity-000007','000007.OF','138e20c8-a626-4fae-b24b-96f37c75033a'),
    ('entity-000003','000003.OF',NULL),
    ('entity-000004','000004.OF',NULL),
    ('entity-000005','000005.OF',NULL),
    ('entity-000006','000006.OF',NULL),
    ('entity-000008','000008.OF',NULL),
    ('entity-000009','000009.OF',NULL),
    ('entity-000010','000010.OF',NULL),
    ('entity-000011','000011.OF',NULL),
    ('entity-000012','000012.OF',NULL),
    ('entity-000013','000013.OF',NULL)
)
INSERT INTO fund_share_classes (
  id, entity_id, fund_id, wind_code, share_class, fee_class,
  currency, is_primary, status, source, source_updated_at, raw_data, updated_at
)
SELECT
  'share-' || fr.wind_code,
  fe.id,
  coalesce(fr.fund_id, f.id::text),
  fr.wind_code,
  'A',
  'front_fee',
  'CNY',
  true,
  'active',
  'research_taxonomy_seed',
  '2026-06-14'::date,
  '{"shareClassMergePolicy":"同一主从份额以 fund_entities 为研究主对象"}'::jsonb,
  now()
FROM fund_rows fr
JOIN fund_entities fe ON fe.canonical_code = fr.canonical_code
LEFT JOIN funds f ON f.wind_code = fr.wind_code
ON CONFLICT (wind_code) DO UPDATE SET
  entity_id = EXCLUDED.entity_id,
  fund_id = EXCLUDED.fund_id,
  share_class = EXCLUDED.share_class,
  fee_class = EXCLUDED.fee_class,
  currency = EXCLUDED.currency,
  is_primary = EXCLUDED.is_primary,
  status = EXCLUDED.status,
  source = EXCLUDED.source,
  source_updated_at = EXCLUDED.source_updated_at,
  raw_data = EXCLUDED.raw_data,
  updated_at = now();

WITH peer_rows(peer_key, peer_name, strategy_family_key, asset_class, active_passive, benchmark_code, benchmark_name, inclusion_rules, exclusion_rules, minimum_peer_count) AS (
  VALUES
    ('peer-active-equity-core-large-5y','主动权益-核心均衡-大规模-5年以上','active_equity_core','equity','active','CSI800','中证800','{"layers":{"strategyFamily":"active_equity_core","style":["核心","均衡"],"scaleBucket":"large","ageBucket":"5y_plus"},"mustHave":["benchmark_mapping","style_tags","scale_bucket","established_at"]}'::jsonb,'{"exclude":["指数基金","行业主题基金","纯债","货币","QDII"]}'::jsonb,5),
    ('peer-active-equity-core-mid-5y','主动权益-核心均衡-中规模-5年以上','active_equity_core','equity','active','CSI800','中证800','{"layers":{"strategyFamily":"active_equity_core","style":["核心","均衡","稳健成长"],"scaleBucket":"mid","ageBucket":"5y_plus"},"mustHave":["benchmark_mapping","style_tags","scale_bucket","established_at"]}'::jsonb,'{"exclude":["指数基金","行业主题基金","纯债","货币","QDII"]}'::jsonb,5),
    ('peer-active-equity-sector-mid-3y','主动权益-行业主题-中规模-3年以上','active_equity_sector','equity','active','CSI_THEME','主题/行业指数','{"layers":{"strategyFamily":"active_equity_sector","style":["科技","成长","行业主题"],"scaleBucket":"mid","ageBucket":"3y_plus"},"mustHave":["sector_exposure","style_tags","scale_bucket","established_at"]}'::jsonb,'{"exclude":["宽基指数","纯债","货币"]}'::jsonb,5),
    ('peer-active-equity-sector-small-5y','主动权益-行业主题-小规模-5年以上','active_equity_sector','equity','active','CSI_SECTOR','行业主题指数','{"layers":{"strategyFamily":"active_equity_sector","style":["行业主题","医药","产业趋势"],"scaleBucket":"small","ageBucket":"5y_plus"},"mustHave":["sector_exposure","style_tags","scale_bucket","established_at"]}'::jsonb,'{"exclude":["宽基指数","纯债","货币"]}'::jsonb,5),
    ('peer-fixed-income-credit-mid-duration','固收-信用债-中久期','fixed_income_credit','fixed_income','active','CBA_CREDIT','中债信用债总财富指数','{"layers":{"strategyFamily":"fixed_income_credit","durationBucket":"medium","creditBucket":"credit"},"mustHave":["duration","rating_distribution","issuer_concentration"]}'::jsonb,'{"exclude":["权益基金","货币","QDII"]}'::jsonb,5),
    ('peer-fixed-income-credit-holding-period','固收-信用债-持有期','fixed_income_credit','fixed_income','active','CBA_INDUSTRIAL','中债产业债总财富指数','{"layers":{"strategyFamily":"fixed_income_credit","holdingPeriod":"1y","creditBucket":"industrial"},"mustHave":["duration","rating_distribution","holding_period"]}'::jsonb,'{"exclude":["权益基金","货币","QDII"]}'::jsonb,5),
    ('peer-index-hs300','指数-沪深300','index_broad','index','passive','000300.SH','沪深300','{"layers":{"sameIndex":"000300.SH","shareClass":"A","tracking":"passive"},"mustHave":["tracking_error","expense_ratio","same_index_peers"]}'::jsonb,'{"exclude":["主动权益","指数增强","非沪深300"]}'::jsonb,5),
    ('peer-index-csi500','指数-中证500','index_broad','index','passive','000905.SH','中证500','{"layers":{"sameIndex":"000905.SH","shareClass":"A","tracking":"passive"},"mustHave":["tracking_error","expense_ratio","same_index_peers"]}'::jsonb,'{"exclude":["主动权益","指数增强","非中证500"]}'::jsonb,5),
    ('peer-money-cash-management','货币-现金管理','cash_management','money_market','active','DR007','DR007','{"layers":{"strategyFamily":"cash_management","liquidity":"high","currency":"CNY"},"mustHave":["liquidity_profile","duration","yield_center"]}'::jsonb,'{"exclude":["权益","债券增强","QDII"]}'::jsonb,5),
    ('peer-qdii-global-consumption','QDII-全球消费主题','qdii_global_theme','global','active','MSCI_GLOBAL_CONSUMER','MSCI全球消费','{"layers":{"region":"global","theme":"consumer","currency":["USD","HKD"],"activePassive":"active"},"mustHave":["region_exposure","currency_exposure","overseas_holdings"]}'::jsonb,'{"exclude":["境内权益","境内债券","货币"]}'::jsonb,5)
)
INSERT INTO peer_groups (
  id, key, name, strategy_family_id, asset_class, active_passive,
  benchmark_code, benchmark_name, inclusion_rules, exclusion_rules,
  minimum_peer_count, source, source_updated_at, updated_at
)
SELECT
  pr.peer_key,
  pr.peer_key,
  pr.peer_name,
  sf.id,
  pr.asset_class,
  pr.active_passive,
  pr.benchmark_code,
  pr.benchmark_name,
  pr.inclusion_rules,
  pr.exclusion_rules,
  pr.minimum_peer_count,
  'research_taxonomy_seed',
  '2026-06-14'::date,
  now()
FROM peer_rows pr
JOIN strategy_families sf ON sf.key = pr.strategy_family_key
ON CONFLICT (key) DO UPDATE SET
  name = EXCLUDED.name,
  strategy_family_id = EXCLUDED.strategy_family_id,
  asset_class = EXCLUDED.asset_class,
  active_passive = EXCLUDED.active_passive,
  benchmark_code = EXCLUDED.benchmark_code,
  benchmark_name = EXCLUDED.benchmark_name,
  inclusion_rules = EXCLUDED.inclusion_rules,
  exclusion_rules = EXCLUDED.exclusion_rules,
  minimum_peer_count = EXCLUDED.minimum_peer_count,
  source = EXCLUDED.source,
  source_updated_at = EXCLUDED.source_updated_at,
  updated_at = now();

WITH member_rows(wind_code, peer_group_key, role, matched_rules, confidence) AS (
  VALUES
    ('000002.OF','peer-active-equity-core-large-5y','member','{"matched":["资产类别=equity","策略族谱=active_equity_core","主动/被动=active","规模=large","成立年限=5年以上"],"styleTags":["均衡价值","核心"]}'::jsonb,0.92),
    ('000003.OF','peer-active-equity-core-mid-5y','member','{"matched":["资产类别=equity","策略族谱=active_equity_core","主动/被动=active","规模=mid","成立年限=5年以上"],"styleTags":["稳健成长","偏股混合"]}'::jsonb,0.88),
    ('000007.OF','peer-active-equity-sector-mid-3y','member','{"matched":["资产类别=equity","策略族谱=active_equity_sector","主动/被动=active","规模=mid","成立年限=3年以上"],"styleTags":["科技成长","高波动"]}'::jsonb,0.90),
    ('000004.OF','peer-active-equity-sector-small-5y','member','{"matched":["资产类别=equity","策略族谱=active_equity_sector","主动/被动=active","规模=small","成立年限=5年以上"],"styleTags":["产业趋势","行业主题"]}'::jsonb,0.86),
    ('000012.OF','peer-active-equity-sector-small-5y','member','{"matched":["资产类别=equity","策略族谱=active_equity_sector","主动/被动=active","规模=small","成立年限=5年以上"],"styleTags":["医药成长","行业主题"]}'::jsonb,0.87),
    ('000005.OF','peer-fixed-income-credit-mid-duration','member','{"matched":["资产类别=fixed_income","策略族谱=fixed_income_credit","久期=中长期","信用=信用债"],"styleTags":["信用债","中长期"]}'::jsonb,0.91),
    ('000006.OF','peer-fixed-income-credit-mid-duration','member','{"matched":["资产类别=fixed_income","策略族谱=fixed_income_credit","久期=中长期","信用=利率债稳健"],"styleTags":["利率债","稳健收益"]}'::jsonb,0.82),
    ('000013.OF','peer-fixed-income-credit-holding-period','member','{"matched":["资产类别=fixed_income","策略族谱=fixed_income_credit","持有期=1年","信用=产业债"],"styleTags":["产业债","持有期"]}'::jsonb,0.89),
    ('000008.OF','peer-index-hs300','member','{"matched":["资产类别=index","策略族谱=index_broad","同指数=沪深300","主动/被动=passive"],"styleTags":["沪深300","宽基"]}'::jsonb,0.95),
    ('000009.OF','peer-index-csi500','member','{"matched":["资产类别=index","策略族谱=index_broad","同指数=中证500","主动/被动=passive"],"styleTags":["中证500","宽基"]}'::jsonb,0.95),
    ('000010.OF','peer-money-cash-management','member','{"matched":["资产类别=money_market","策略族谱=cash_management","流动性=high"],"styleTags":["现金管理","流动性"]}'::jsonb,0.93),
    ('000011.OF','peer-qdii-global-consumption','member','{"matched":["资产类别=global","策略族谱=qdii_global_theme","区域=global","主题=consumer"],"styleTags":["全球消费","QDII"]}'::jsonb,0.90)
)
INSERT INTO peer_group_members (
  id, peer_group_id, entity_id, role, matched_rules, excluded_rules,
  sample_as_of_date, confidence, source, updated_at
)
SELECT
  'peer-member-' || mr.wind_code,
  pg.id,
  fe.id,
  mr.role,
  mr.matched_rules,
  '{"excluded":[]}'::jsonb,
  '2026-06-14'::date,
  mr.confidence,
  'research_taxonomy_seed',
  now()
FROM member_rows mr
JOIN fund_share_classes fsc ON fsc.wind_code = mr.wind_code
JOIN fund_entities fe ON fe.id = fsc.entity_id
JOIN peer_groups pg ON pg.key = mr.peer_group_key
ON CONFLICT (peer_group_id, entity_id) DO UPDATE SET
  role = EXCLUDED.role,
  matched_rules = EXCLUDED.matched_rules,
  excluded_rules = EXCLUDED.excluded_rules,
  sample_as_of_date = EXCLUDED.sample_as_of_date,
  confidence = EXCLUDED.confidence,
  source = EXCLUDED.source,
  updated_at = now();
