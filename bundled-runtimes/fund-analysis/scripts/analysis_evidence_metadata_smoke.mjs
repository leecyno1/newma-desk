#!/usr/bin/env node
// scripts/analysis_evidence_metadata_smoke.mjs
//
// AI 分析证据版本兼容 smoke test
// -----------------------------------------
// 验证 lib/analysis-evidence-metadata.ts 的 analysisEvidenceMetadata() 在三类
// 历史 data_sources 形态下都能：
//   1) 不抛异常
//   2) 保留所有已存在字段
//   3) 对缺失字段返回 null / 空数组，不返回 undefined
//   4) 增补新字段（模拟未来 schema 演化）不破坏历史回放
//
// 运行：
//   node --experimental-strip-types scripts/analysis_evidence_metadata_smoke.mjs
// 该 smoke 无需 DB 或后端。

import assert from 'node:assert/strict'
import { analysisEvidenceMetadata } from '../lib/analysis-evidence-metadata.ts'

const CASES = [
  {
    name: 'modern (2026-08): assessment_summary at top level',
    input: {
      research_snapshot: { some_other_field: 1 },
      assessment_summary: {
        score: 78.5,
        grade: 'B+',
        peer_rank: 42,
        peer_count: 128,
        verdict: '同类中位偏上',
        style_evidence: {
          status: 'complete',
          scope: 'holdings+memo',
          quarter: '2026Q1',
          labels: ['大盘', '价值'],
          memo_labels: ['稳健'],
        },
        research_evidence: { status: 'partial', note: '仅经理层纪要 1 份' },
        attribution_evidence: {
          status: 'complete',
          headline: 'Brinson: 配置贡献 +1.2%',
          detail: '选择效应 -0.3%',
          coverage: 0.82,
          formal_barra_ready: false,
          barra_descriptor_ready: true,
        },
      },
    },
    expect: {
      evaluation_score: 78.5,
      evaluation_grade: 'B+',
      peer_rank: 42,
      peer_count: 128,
      evaluation_verdict: '同类中位偏上',
      style_evidence_status: 'complete',
      style_evidence_scope: 'holdings+memo',
      style_evidence_quarter: '2026Q1',
      style_labels: ['大盘', '价值'],
      memo_style_labels: ['稳健'],
      research_evidence_status: 'partial',
      research_evidence_note: '仅经理层纪要 1 份',
      attribution_evidence_status: 'complete',
      attribution_evidence_headline: 'Brinson: 配置贡献 +1.2%',
      attribution_evidence_detail: '选择效应 -0.3%',
      attribution_disclosure_coverage: 0.82,
      formal_barra_ready: false,
      barra_descriptor_ready: true,
    },
  },
  {
    name: 'legacy (2026-06): assessment_summary nested under research_snapshot',
    input: {
      research_snapshot: {
        assessment_summary: {
          score: 65,
          grade: 'B',
          style_evidence: { status: 'partial', labels: ['均衡'] },
          attribution_evidence: { status: 'insufficient', coverage: 0.35 },
        },
      },
    },
    expect: {
      evaluation_score: 65,
      evaluation_grade: 'B',
      style_evidence_status: 'partial',
      style_labels: ['均衡'],
      attribution_evidence_status: 'insufficient',
      attribution_disclosure_coverage: 0.35,
      // Fields absent in legacy input should still be present with null defaults
      peer_rank: null,
      peer_count: null,
      evaluation_verdict: null,
      research_evidence_status: null,
      research_evidence_note: null,
      attribution_evidence_headline: null,
      attribution_evidence_detail: null,
      formal_barra_ready: false,
      barra_descriptor_ready: false,
      memo_style_labels: [],
    },
  },
  {
    name: 'minimal (2026-04): only bare research_snapshot, no assessment fields',
    input: { research_snapshot: {} },
    expect: {
      evaluation_score: null,
      evaluation_grade: null,
      peer_rank: null,
      peer_count: null,
      evaluation_verdict: null,
      style_evidence_status: null,
      style_evidence_scope: null,
      style_evidence_quarter: null,
      style_labels: [],
      memo_style_labels: [],
      research_evidence_status: null,
      research_evidence_note: null,
      attribution_evidence_status: null,
      attribution_evidence_headline: null,
      attribution_evidence_detail: null,
      attribution_disclosure_coverage: null,
      formal_barra_ready: false,
      barra_descriptor_ready: false,
    },
  },
  {
    name: 'future-shape: unknown extra keys must not crash',
    input: {
      assessment_summary: {
        score: 71,
        // extra futuristic fields that current metadata does NOT read
        style_evidence: { status: 'complete', labels: ['成长'], drift_alert: 'moderate' },
        attribution_evidence: { status: 'complete', coverage: 0.9, new_factor_split: {} },
        holdings_change_alert: 'concentration_up',
      },
      research_snapshot: { new_2027_field: true },
    },
    expect: {
      evaluation_score: 71,
      style_evidence_status: 'complete',
      style_labels: ['成长'],
      attribution_evidence_status: 'complete',
      attribution_disclosure_coverage: 0.9,
    },
  },
  {
    name: 'null / undefined / non-object inputs must not throw',
    input: null,
    expect: {
      evaluation_score: null,
      style_labels: [],
      memo_style_labels: [],
      formal_barra_ready: false,
      barra_descriptor_ready: false,
    },
  },
]

let failed = 0
for (const testCase of CASES) {
  try {
    const result = analysisEvidenceMetadata(testCase.input ?? {})
    // Ensure result is an object
    assert.equal(typeof result, 'object', `${testCase.name}: result not object`)
    assert.notEqual(result, null, `${testCase.name}: result null`)

    for (const [key, expected] of Object.entries(testCase.expect)) {
      const actual = result[key]
      if (Array.isArray(expected)) {
        assert.deepStrictEqual(actual, expected, `${testCase.name}: field '${key}' array mismatch`)
      } else {
        assert.strictEqual(actual, expected, `${testCase.name}: field '${key}' expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`)
      }
    }

    // Verify defensive defaults: fields that should always be present
    const REQUIRED_KEYS = [
      'evaluation_score', 'evaluation_grade', 'peer_rank', 'peer_count', 'evaluation_verdict',
      'style_evidence_status', 'style_labels', 'memo_style_labels',
      'research_evidence_status', 'attribution_evidence_status',
      'attribution_disclosure_coverage', 'formal_barra_ready', 'barra_descriptor_ready',
    ]
    for (const key of REQUIRED_KEYS) {
      assert.notEqual(typeof result[key], 'undefined', `${testCase.name}: required key '${key}' missing (undefined)`)
    }

    console.log(`  ✓ ${testCase.name}`)
  } catch (err) {
    failed += 1
    console.error(`  ✗ ${testCase.name}`)
    console.error(`    ${err instanceof Error ? err.message : String(err)}`)
  }
}

if (failed) {
  console.error(`\n${failed} case(s) failed.`)
  process.exit(1)
}
console.log(`\nAll ${CASES.length} evidence metadata cases passed.`)
