import assert from 'node:assert/strict'
import test from 'node:test'
import {
  LLM_USAGE_STAGE_ORDER,
  formatHitRate,
  formatTokenCount,
  llmUsageHitRate,
  llmUsageRows,
} from '../src/llmUsage.js'

const bucket = (calls, prompt, completion, hit, miss) => ({
  calls,
  prompt_tokens: prompt,
  completion_tokens: completion,
  cache_hit_tokens: hit,
  cache_miss_tokens: miss,
})

test('llmUsageRows keeps fixed stage order, skips unused stages and appends total', () => {
  const rows = llmUsageRows({
    total: bucket(3, 2500, 350, 100, 2400),
    by_stage: {
      // 故意打乱顺序且缺 blueprint/review 阶段
      mindmap: bucket(1, 500, 50, 0, 500),
      draft: bucket(1, 500, 50, 0, 500),
      understand: bucket(1, 1500, 250, 100, 1400),
      other: bucket(0, 0, 0, 0, 0),
    },
  })

  assert.deepEqual(rows.map(row => row.stage), ['understand', 'draft', 'mindmap', 'total'])
  assert.equal(rows[3].prompt_tokens, 2500)
  assert.deepEqual(LLM_USAGE_STAGE_ORDER, [
    'understand', 'blueprint', 'draft', 'review', 'mindmap', 'other',
  ])
})

test('llmUsageRows returns empty array when no usage data (section hidden)', () => {
  assert.deepEqual(llmUsageRows(undefined), [])
  assert.deepEqual(llmUsageRows({}), [])
  assert.deepEqual(llmUsageRows({ total: bucket(0, 0, 0, 0, 0), by_stage: {} }), [])
})

test('llmUsageHitRate computes hit/(hit+miss) and null without input', () => {
  assert.equal(llmUsageHitRate(bucket(1, 1000, 0, 100, 900)), 0.1)
  assert.equal(llmUsageHitRate(bucket(1, 0, 0, 0, 0)), null)
})

test('formatHitRate renders one-decimal percent or dash', () => {
  assert.equal(formatHitRate(0.125), '12.5%')
  assert.equal(formatHitRate(null), '-')
  assert.equal(formatHitRate(undefined), '-')
})

test('formatTokenCount groups thousands and coerces non-numbers', () => {
  assert.equal(formatTokenCount(3200000), (3200000).toLocaleString())
  assert.equal(formatTokenCount(undefined), '0')
})
