import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing: ${expected}`)
}

const driftService = read('backend/services/holding_style_drift_service.py')
const snapshotService = read('backend/services/fund_research_snapshot_service.py')
const detailPage = read('app/(dashboard)/funds/[id]/page.tsx')
const syncScript = read('backend/scripts/sync_holding_style_snapshots.py')
const scheduledUpdate = read('scripts/scheduled_update.sh')
const evaluationSnapshotScript = read('backend/scripts/save_evaluation_snapshots.py')

// 漂移算法核心边界：相邻披露期同类分位对比，不进入评分
assertIncludes(driftService, 'READY_STATUSES = {"peer_percentile_ready", "peer_percentile_neutral"}', 'drift requires percentile-ready snapshots')
assertIncludes(driftService, 'adjacent_disclosed_holding_style_percentile_change_v1', 'drift methodology versioned')
assertIncludes(driftService, 'changed_factor_count >= 3 or max_change >= 0.40', 'drift high threshold')
assertIncludes(driftService, 'included_in_score', 'drift discloses score boundary')
assertIncludes(driftService, '相邻持仓期的专业同类组不同', 'drift blocks cross-peer-group comparison')

// 研究快照集成：漂移证据进入详情快照
assertIncludes(snapshotService, 'from services.holding_style_drift_service import HoldingStyleDriftService', 'research snapshot imports drift service')
assertIncludes(snapshotService, '"style_drift_evidence": style_drift_evidence', 'research snapshot exposes style drift evidence')

// 前端消费：基金详情页渲染漂移证据
assertIncludes(detailPage, 'styleDriftEvidencePayload', 'fund detail reads style drift evidence payload')
assertIncludes(detailPage, "styleDriftEvidence: {", 'fund detail maps style drift evidence')

// 数据管道：快照生成脚本与每日评价快照积累注册进调度
assertIncludes(syncScript, 'include-existing', 'holding style snapshot sync supports include-existing rerun')
assertIncludes(scheduledUpdate, 'evaluation:snapshots|daily|.venv/bin/python backend/scripts/save_evaluation_snapshots.py', 'scheduled update runs daily evaluation snapshots')
assertIncludes(evaluationSnapshotScript, 'ORDER BY MAX(created_at) DESC', 'evaluation snapshot candidates prefer continuity')
assertIncludes(evaluationSnapshotScript, 'NOT IN (SELECT wind_code FROM fund_evaluation_snapshots)', 'evaluation snapshot script adds fresh funds only after continuity pool')

console.log('OK holding style drift evidence chain stays wired from snapshots to fund detail with daily accumulation')
