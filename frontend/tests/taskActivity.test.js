import assert from 'node:assert/strict'
import test from 'node:test'
import {
  eventLogText,
  snapshotActivities,
  upsertActivity,
} from '../src/taskActivity.js'

test('reads the backend log line field before compatibility aliases', () => {
  assert.equal(eventLogText({ line: '真实日志', message: '旧字段' }), '真实日志')
  assert.equal(eventLogText({ message: '兼容消息' }), '兼容消息')
  assert.equal(eventLogText({ msg: '兼容短消息' }), '兼容短消息')
  assert.equal(eventLogText({}), '')
})

test('restores completed and running activities from persisted node snapshots', () => {
  const activities = snapshotActivities({
    created_at: '2026-07-29T10:00:00',
    node_statuses: {
      download: { status: 'skipped' },
      extract_audio: {
        status: 'completed',
        started_at: '2026-07-29T10:00:01',
        finished_at: '2026-07-29T10:00:06',
      },
      asr: {
        status: 'running',
        started_at: '2026-07-29T10:00:06',
      },
      note: { status: 'pending' },
    },
  })

  assert.deepEqual(activities.map(item => [item.node, item.status]), [
    ['download', 'skipped'],
    ['extract_audio', 'completed'],
    ['asr', 'running'],
  ])
  assert.equal(activities[1].timestamp, '2026-07-29T10:00:06')
  assert.equal(activities[2].timestamp, '2026-07-29T10:00:06')
})

test('upserts lifecycle state without duplicating the same activity id', () => {
  const first = upsertActivity([], { id: 'node:asr:running', status: 'running' })
  const second = upsertActivity(first, {
    id: 'node:asr:running',
    status: 'running',
    message: '50%',
  })
  assert.equal(second.length, 1)
  assert.equal(second[0].message, '50%')
})
