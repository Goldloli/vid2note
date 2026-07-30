export const TASK_NODE_ORDER = [
  'download',
  'extract_audio',
  'asr',
  'note',
  'mindmap',
  'cleanup',
]

export function eventLogText(payload = {}) {
  return String(payload.line || payload.message || payload.msg || '').trim()
}

export function snapshotActivities(task = {}) {
  const statuses = task.node_statuses || {}
  const activities = []
  TASK_NODE_ORDER.forEach((node, order) => {
    const state = statuses[node] || {}
    const status = state.status || 'pending'
    if (status === 'pending') return
    let timestamp = state.started_at || task.created_at || ''
    if (status === 'completed' || status === 'failed') {
      timestamp = state.finished_at || timestamp
    }
    activities.push({
      id: `node:${node}:${status}`,
      node,
      status,
      order,
      timestamp,
      error: state.error || '',
      source: 'snapshot',
    })
  })
  return activities
}

export function upsertActivity(activities, activity, limit = 80) {
  if (!activity?.id) return activities
  const next = activities.filter(item => item.id !== activity.id)
  next.push(activity)
  return next.slice(-limit)
}
