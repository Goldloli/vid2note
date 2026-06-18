const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const test = require('node:test')

const { PythonService } = require('../../src/main/python-service')

class FakeChild extends EventEmitter {
  constructor() {
    super()
    this.signals = []
  }

  kill(signal) {
    this.signals.push(signal)
  }
}

class FakeClock {
  constructor() {
    this.callback = null
  }

  setTimeout(callback) {
    this.callback = callback
    return 1
  }

  clearTimeout() {
    this.callback = null
  }

  advance() {
    this.callback?.()
  }
}

test('stop escalates only after the grace period', () => {
  const child = new FakeChild()
  const clock = new FakeClock()
  const service = new PythonService({ child, clock, graceMs: 30_000 })

  service.stop()
  assert.deepEqual(child.signals, ['SIGTERM'])

  clock.advance()
  assert.deepEqual(child.signals, ['SIGTERM', 'SIGKILL'])
})

test('process exit cancels forced termination', () => {
  const child = new FakeChild()
  const clock = new FakeClock()
  const service = new PythonService({ child, clock, graceMs: 30_000 })

  service.stop()
  child.emit('exit', 0)
  clock.advance()

  assert.deepEqual(child.signals, ['SIGTERM'])
})
