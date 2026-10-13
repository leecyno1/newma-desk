import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) {
    throw new Error(`${label} still contains forbidden text: ${forbidden}`)
  }
}

const peerService = read('backend/services/peer_comparison_service.py')
const detailClient = read('app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx')

assertIncludes(peerService, 'MIN_VALID_PEERS = 5', 'peer percentile minimum sample gate')
assertIncludes(peerService, 'if len(valid) < minimum:', 'peer percentile refuses small valid sample')
assertIncludes(peerService, '"sample_status": "insufficient_peer_sample"', 'peer percentile labels small sample')
assertIncludes(peerService, '"minimum_valid_peer_count": minimum_peer_count', 'peer percentile exposes minimum sample size')
assertIncludes(peerService, '"usable_metric_count": self._usable_metric_count(metrics)', 'peer percentile exposes usable metric count')
assertIncludes(peerService, '"insufficient_metric_count": self._insufficient_metric_count(metrics)', 'peer percentile exposes thin metric evidence count')
assertIncludes(peerService, '"peer_metric_gap": self._peer_metric_gap(', 'peer percentile exposes actionable metric gap')
assertIncludes(peerService, 'def _sample_status', 'peer percentile exposes aggregate sample status')
assertIncludes(peerService, 'def _usable_metric_count', 'peer percentile counts usable metrics')
assertIncludes(peerService, 'def _peer_metric_gap', 'peer percentile computes peer metric gap')
assertIncludes(peerService, 'def _suggest_metric_sync_funds', 'peer percentile suggests syncable peers')
assertIncludes(peerService, '"suggested_sync_codes": [fund["wind_code"] for fund in suggested_funds]', 'peer percentile exposes suggested peer sync codes')
assertIncludes(peerService, '"suggested_sync_funds": suggested_funds', 'peer percentile exposes suggested peer sync funds')
assertIncludes(peerService, '"next_action": "sync_peer_nav_and_rolling_metrics"', 'peer percentile gives metric sync next action')
assertIncludes(peerService, 'repo.get_latest_panels("fund", missing_codes)', 'peer percentile batch-loads metric panels')
assertIncludes(peerService, 'scoring_map = self._fast_peer_score_map(', 'peer percentile avoids per-peer formal scoring')
assertIncludes(peerService, '"professional_score_source": "category_specific_peer_metric_proxy"', 'peer percentile discloses fast proxy score source')
assertIncludes(peerService, 'def _fast_peer_score', 'peer percentile defines fast peer score proxy')
assertNotIncludes(peerService, '100.0 if peer_count == 1', 'peer percentile must not treat single sample as top percentile')
assertNotIncludes(peerService, 'scoring_map = self._scoring_map(peer_codes)', 'peer percentile must not call slow formal scoring for full peer universe')

// 详情页现行同类样本边界：样本不足时不输出综合分、不贴同类标签（e3478bb 研究画像化后
// 的锚点；补同类指标的 sync 行为由评价覆盖页与市场工作台承担）。
assertIncludes(detailClient, "evaluation.sampleStatus !== 'sufficient' && evaluation.validPeerCount < evaluation.minimumPeerCount", 'fund detail gates scores on peer sample status')
assertIncludes(detailClient, '同类有效样本', 'fund detail discloses the insufficient peer sample')
assertIncludes(detailClient, '暂不输出综合分', 'fund detail refuses scores on small peer samples')
assertIncludes(detailClient, '最低需要', 'fund detail discloses the holding-profile minimum sample')
assertIncludes(detailClient, '不贴“偏高/偏低”标签', 'fund detail refuses peer labels on small samples')

console.log('OK peer percentile small-sample gate avoids false peer advantage')
