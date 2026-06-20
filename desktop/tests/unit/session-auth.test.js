const assert = require('node:assert/strict')
const test = require('node:test')

const { createSessionToken, withSessionToken } = require('../../src/main/session-auth')

test('creates a different high-entropy token for each app session', () => {
  const first = createSessionToken()
  const second = createSessionToken()

  assert.notEqual(first, second)
  assert.ok(first.length >= 43)
  assert.match(first, /^[A-Za-z0-9_-]+$/)
})

test('passes the session token only through the backend environment', () => {
  const environment = withSessionToken({ PATH: '/bin' }, 'secret-session-token')

  assert.deepEqual(environment, {
    PATH: '/bin',
    VID2NOTE_API_TOKEN: 'secret-session-token',
  })
})
