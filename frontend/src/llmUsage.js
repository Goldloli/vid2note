// LLM 用量展示纯逻辑(openspec「LLM 用量观测」)
// 数据来源:任务详情 task.llm_usage(total / by_stage / by_operation),
// 由后端 runner.LlmUsageAggregator 聚合落库。本文件无依赖,便于 node --test 单测。

// 阶段固定展示顺序(与后端 classify_llm_operation 的阶段键一致)
export const LLM_USAGE_STAGE_ORDER = [
  'understand',
  'blueprint',
  'draft',
  'review',
  'mindmap',
  'other',
]

// 输入命中率 = 缓存命中 ÷ (命中 + 未命中);无输入时返回 null(界面显示 -)
export function llmUsageHitRate(bucket) {
  const hit = Number(bucket?.cache_hit_tokens || 0)
  const miss = Number(bucket?.cache_miss_tokens || 0)
  const total = hit + miss
  return total > 0 ? hit / total : null
}

// 生成表格行:有调用的阶段(固定顺序)+ 总计行;无数据返回空数组(区块不渲染)
export function llmUsageRows(llmUsage) {
  const byStage = llmUsage?.by_stage || {}
  const rows = LLM_USAGE_STAGE_ORDER
    .map(stage => ({ stage, ...(byStage[stage] || {}) }))
    .filter(row => (row.calls || 0) > 0)
  const total = llmUsage?.total || {}
  if ((total.calls || 0) > 0) rows.push({ stage: 'total', ...total })
  return rows
}

// token 数字格式化(千分位;非数字归 0)
export function formatTokenCount(value) {
  return Number(value || 0).toLocaleString()
}

// 命中率格式化(无输入显示 -,否则保留一位小数百分比)
export function formatHitRate(rate) {
  return rate === null || rate === undefined ? '-' : `${(rate * 100).toFixed(1)}%`
}
