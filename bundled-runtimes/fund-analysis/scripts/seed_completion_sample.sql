CREATE TABLE IF NOT EXISTS fund_sales_rules (
  wind_code text NOT NULL,
  platform text NOT NULL DEFAULT 'manual',
  purchase_status text NOT NULL DEFAULT 'unknown',
  purchase_status_label text NOT NULL DEFAULT '申购待核',
  min_purchase_amount numeric,
  min_sip_amount numeric,
  daily_limit_amount numeric,
  purchase_fee_rate numeric,
  redemption_fee_rules jsonb NOT NULL DEFAULT '[]'::jsonb,
  sales_service_fee_rate numeric,
  risk_level text,
  supports_sip boolean,
  source_url text,
  source_updated_at date,
  notes text,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (wind_code, platform)
);

CREATE INDEX IF NOT EXISTS fund_sales_rules_wind_code_idx ON fund_sales_rules (wind_code);

INSERT INTO funds (
  id, wind_code, name, type, manager_ids, nav, nav_date, total_asset,
  establishment_date, performance_data, risk_metrics, raw_data, updated_at
) VALUES
  ('ac546c3f-6b2b-4017-8fe3-21b74dc5bf77','000002.OF','易方达均衡价值股票','stock',ARRAY['M002'],2.1035,'2026-05-29',132.80,'2015-06-12','{"return_1y":0.164,"sharpe_ratio":1.41,"annualized_return_1y":0.164}'::jsonb,'{"volatility":0.221,"max_drawdown":-0.196}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  ('138e20c8-a626-4fae-b24b-96f37c75033a','000007.OF','富国科技成长股票','stock',ARRAY['M007'],1.9264,'2026-05-29',63.90,'2020-07-17','{"return_1y":0.210,"sharpe_ratio":1.35,"annualized_return_1y":0.210}'::jsonb,'{"volatility":0.290,"max_drawdown":-0.240}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000003.OF','广发稳健增长混合','hybrid',ARRAY['M003'],1.4820,'2026-05-29',88.20,'2018-03-21','{"return_1y":0.092,"sharpe_ratio":1.02}'::jsonb,'{"volatility":0.165,"max_drawdown":-0.118}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000004.OF','南方产业趋势混合','hybrid',ARRAY['M004'],1.7365,'2026-05-29',47.60,'2019-11-08','{"return_1y":0.128,"sharpe_ratio":1.18}'::jsonb,'{"volatility":0.205,"max_drawdown":-0.151}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000005.OF','博时信用优选债券','bond',ARRAY['M005'],1.1288,'2026-05-29',52.40,'2016-09-23','{"return_1y":0.041,"sharpe_ratio":1.66}'::jsonb,'{"volatility":0.038,"max_drawdown":-0.021}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000006.OF','招商安心收益债券','bond',ARRAY['M006'],1.0963,'2026-05-29',29.70,'2014-04-18','{"return_1y":0.035,"sharpe_ratio":1.52}'::jsonb,'{"volatility":0.031,"max_drawdown":-0.018}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000008.OF','华夏沪深300指数','index',ARRAY['M008'],1.3142,'2026-05-29',156.00,'2012-05-04','{"return_1y":0.103,"sharpe_ratio":0.95}'::jsonb,'{"volatility":0.188,"max_drawdown":-0.132}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000009.OF','嘉实中证500指数','index',ARRAY['M009'],1.0821,'2026-05-29',72.30,'2017-01-11','{"return_1y":0.077,"sharpe_ratio":0.82}'::jsonb,'{"volatility":0.214,"max_drawdown":-0.166}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000010.OF','天弘现金管家货币','money',ARRAY['M010'],1.0000,'2026-05-29',242.00,'2013-08-15','{"return_1y":0.018,"sharpe_ratio":2.20}'::jsonb,'{"volatility":0.004,"max_drawdown":-0.001}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000011.OF','汇添富全球消费QDII','qdii',ARRAY['M011'],1.2219,'2026-05-29',34.50,'2021-02-05','{"return_1y":0.115,"sharpe_ratio":0.88}'::jsonb,'{"volatility":0.236,"max_drawdown":-0.181}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000012.OF','工银瑞信医疗创新股票','stock',ARRAY['M012'],1.5186,'2026-05-29',41.20,'2019-06-28','{"return_1y":0.087,"sharpe_ratio":0.74}'::jsonb,'{"volatility":0.267,"max_drawdown":-0.214}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW()),
  (gen_random_uuid(),'000013.OF','鹏华产业债一年持有','bond',ARRAY['M013'],1.0528,'2026-05-29',38.90,'2022-10-14','{"return_1y":0.032,"sharpe_ratio":1.44}'::jsonb,'{"volatility":0.029,"max_drawdown":-0.016}'::jsonb,'{"seed":"completion","source":"tushare"}'::jsonb,NOW())
ON CONFLICT (wind_code) DO UPDATE SET
  name = EXCLUDED.name,
  type = EXCLUDED.type,
  manager_ids = EXCLUDED.manager_ids,
  nav = EXCLUDED.nav,
  nav_date = EXCLUDED.nav_date,
  total_asset = EXCLUDED.total_asset,
  establishment_date = EXCLUDED.establishment_date,
  performance_data = EXCLUDED.performance_data,
  risk_metrics = EXCLUDED.risk_metrics,
  raw_data = EXCLUDED.raw_data,
  updated_at = NOW();

INSERT INTO fund_research_profiles (
  wind_code, primary_benchmark, secondary_benchmark, peer_group, style_label,
  strategy_tags, manager_tenure_start, capacity_notes, data_quality_notes, evidence, updated_by
) VALUES
  ('000002.OF','沪深300','中证800','主动权益-大盘均衡','大盘均衡',ARRAY['主动权益','均衡价值','核心观察'],'2023-01-01','132.80 亿规模较大，需关注策略容量与调仓冲击。','基准、同类池、净值日期已校验。','{"source":"completion-seed","confidence":"high"}'::jsonb,'completion-seed'),
  ('000007.OF','中证科技100','中证TMT','主动权益-科技成长','科技成长',ARRAY['主动权益','科技成长','高波动'],'2024-07-01','63.90 亿规模适中，需关注成长风格拥挤度。','基准、同类池、净值日期已校验。','{"source":"completion-seed","confidence":"high"}'::jsonb,'completion-seed'),
  ('000003.OF','偏股混合基金指数','中证800','偏股混合-稳健成长','稳健成长',ARRAY['偏股混合','稳健成长'],'2022-03-01','规模处于可管理区间。','同类池由基金类型与风险收益特征映射。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000004.OF','偏股混合基金指数','中证800','偏股混合-产业趋势','产业趋势',ARRAY['偏股混合','产业趋势'],'2021-11-01','规模偏小，需关注申赎扰动。','同类池由基金类型与风险收益特征映射。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000005.OF','中债综合财富指数','中债信用债总财富指数','中长期纯债-信用优选','信用债',ARRAY['债券','信用优选'],'2020-06-01','债券流动性整体可控，需跟踪信用利差。','基准映射到债券财富指数。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000006.OF','中债综合财富指数','中债总财富指数','中长期纯债-稳健收益','利率债稳健',ARRAY['债券','稳健收益'],'2019-04-01','规模可管理，久期风险需监控。','基准映射到债券财富指数。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000008.OF','沪深300','沪深300全收益','被动指数-沪深300','宽基指数',ARRAY['指数','沪深300'],'2018-01-01','规模较大但指数基金容量友好。','被动指数基准已确认。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000009.OF','中证500','中证500全收益','被动指数-中证500','中盘指数',ARRAY['指数','中证500'],'2019-01-01','需关注中盘流动性和跟踪误差。','被动指数基准已确认。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000010.OF','货币基金收益率中枢','DR007','货币基金-现金管理','现金管理',ARRAY['货币','现金管理'],'2017-01-01','流动性优先，收益弹性有限。','货币基金基准采用资金利率参照。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000011.OF','MSCI全球消费','标普全球1200消费','QDII-全球消费','全球消费',ARRAY['QDII','全球消费'],'2022-02-01','需关注汇率、海外流动性和额度风险。','QDII 基准按投资区域与主题映射。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000012.OF','中证医药卫生','中证医疗','主动权益-医药主题','医药成长',ARRAY['主动权益','医药主题'],'2023-06-01','行业主题集中度高，容量受细分赛道影响。','主题基准已映射。','{"source":"completion-seed"}'::jsonb,'completion-seed'),
  ('000013.OF','中债综合财富指数','中债产业债总财富指数','持有期债券-产业债','产业债',ARRAY['债券','持有期'],'2023-10-01','持有期产品需关注负债端稳定性。','持有期债基基准已映射。','{"source":"completion-seed"}'::jsonb,'completion-seed')
ON CONFLICT (wind_code) DO UPDATE SET
  primary_benchmark = EXCLUDED.primary_benchmark,
  secondary_benchmark = EXCLUDED.secondary_benchmark,
  peer_group = EXCLUDED.peer_group,
  style_label = EXCLUDED.style_label,
  strategy_tags = EXCLUDED.strategy_tags,
  manager_tenure_start = EXCLUDED.manager_tenure_start,
  capacity_notes = EXCLUDED.capacity_notes,
  data_quality_notes = EXCLUDED.data_quality_notes,
  evidence = EXCLUDED.evidence,
  updated_by = EXCLUDED.updated_by,
  updated_at = NOW();

INSERT INTO scores (target_type, target_id, dimension, score, weight, calculation_method, details)
SELECT 'fund', '000002.OF', 'overall', 82.35, 1.00, 'completion_validation',
       '{"summary":"收益与风险调整表现良好，适合进入观察池。"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM scores
  WHERE target_type = 'fund' AND target_id = '000002.OF' AND calculation_method = 'completion_validation'
);

INSERT INTO ai_analysis_reports (
  id, target_type, target_id, report_type, content, data_sources, research_reports_used, generation_params
)
SELECT '0db3b1b2-abd9-4290-9564-26d32074dd8b', 'fund',
       'ac546c3f-6b2b-4017-8fe3-21b74dc5bf77', 'completion_summary',
       '完成验收样本报告：易方达均衡价值股票近一年收益稳健，最大回撤可控，但仍需跟踪权益仓位波动。',
       '{"source":"completion-validation"}'::jsonb,
       ARRAY['completion-validation'],
       '{"mode":"deterministic","includeReports":true,"reportsCount":1,"evidenceCount":1,"model":"deterministic"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM ai_analysis_reports WHERE id = '0db3b1b2-abd9-4290-9564-26d32074dd8b'
);

INSERT INTO fund_pools (id, name, description, created_by, is_default)
VALUES ('d6b928c6-f445-42b5-8aab-bd8a7f518f77', '默认候选池', '由全市场浏览器自动创建', 'completion-seed', true)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  is_default = EXCLUDED.is_default,
  updated_at = NOW();

INSERT INTO pool_members (
  id, pool_id, fund_id, status, reason, latest_conclusion, evidence,
  risk_notes, next_review_date, created_by, updated_by
)
VALUES (
  'a3d98d8a-df03-42cf-a412-65189a8cc66d',
  'd6b928c6-f445-42b5-8aab-bd8a7f518f77',
  '138e20c8-a626-4fae-b24b-96f37c75033a',
  'watch',
  '完成验收：全市场浏览器初筛入池',
  '完成验收：已由候选进入观察。',
  '{"source":"completion-smoke","decision":"watch","checkedAt":"2026-06-03"}'::jsonb,
  '关注科技成长风格波动与持仓集中度。',
  '2026-07-15',
  'completion-seed',
  'completion-seed'
)
ON CONFLICT (pool_id, fund_id) DO UPDATE SET
  status = EXCLUDED.status,
  reason = EXCLUDED.reason,
  latest_conclusion = EXCLUDED.latest_conclusion,
  evidence = EXCLUDED.evidence,
  risk_notes = EXCLUDED.risk_notes,
  next_review_date = EXCLUDED.next_review_date,
  updated_by = EXCLUDED.updated_by,
  updated_at = NOW();

INSERT INTO alert_rules (id, name, rule_type, scope_type, scope_id, threshold, enabled, created_by)
VALUES (
  'd7fc0956-9f44-4e6e-ba99-3d2aca7c33a8',
  '回撤预警-smoke',
  'drawdown',
  'pool',
  'd6b928c6-f445-42b5-8aab-bd8a7f518f77',
  '{"max_drawdown":-0.15}'::jsonb,
  true,
  'completion-seed'
)
ON CONFLICT (id) DO UPDATE SET
  enabled = EXCLUDED.enabled,
  threshold = EXCLUDED.threshold,
  updated_at = NOW();

INSERT INTO alert_events (
  id, rule_id, fund_id, pool_member_id, event_type, severity, title,
  message, status, resolved_at, details
)
VALUES (
  'afb582bd-c8d0-47d7-afeb-b1d7716144ac',
  'd7fc0956-9f44-4e6e-ba99-3d2aca7c33a8',
  '138e20c8-a626-4fae-b24b-96f37c75033a',
  'a3d98d8a-df03-42cf-a412-65189a8cc66d',
  'drawdown',
  'high',
  '回撤超过阈值',
  '当前最大回撤 -0.24，已超过监控阈值',
  'new',
  NULL,
  '{"current_drawdown":-0.24}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  status = EXCLUDED.status,
  details = EXCLUDED.details,
  message = EXCLUDED.message,
  created_at = NOW();
