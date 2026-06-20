class PythonService {
  constructor({ child = null, clock = globalThis, graceMs = 30_000 } = {}) {
    this.child = child
    this.clock = clock
    this.graceMs = graceMs
    this.forceKillTimer = null
  }

  attach(child) {
    this.child = child
    return child
  }

  stop() {
    const child = this.child
    if (!child || this.forceKillTimer) return

    child.kill('SIGTERM')
    this.forceKillTimer = this.clock.setTimeout(() => {
      if (this.child === child) child.kill('SIGKILL')
      this.forceKillTimer = null
    }, this.graceMs)
    child.once('exit', () => {
      if (this.forceKillTimer) this.clock.clearTimeout(this.forceKillTimer)
      this.forceKillTimer = null
      if (this.child === child) this.child = null
    })
  }
}

module.exports = { PythonService }
