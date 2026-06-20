const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { _electron: electron } = require('playwright')

async function main() {
  const resources = path.resolve('dist-electron/mac-arm64/vid2note.app/Contents/Resources')
  const executable = path.resolve('dist-electron/mac-arm64/vid2note.app/Contents/MacOS/vid2note')
  for (const file of [
    'THIRD_PARTY_NOTICES.md',
    'backend/vid2note-server',
    'backend/_internal/bin/ffmpeg',
    'backend/_internal/bin/yt-dlp',
  ]) assert.equal(fs.existsSync(path.join(resources, file)), true, `missing packaged ${file}`)

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vid2note-package-smoke-'))
  const application = await electron.launch({
    executablePath: executable,
    args: [`--user-data-dir=${path.join(root, 'user-data')}`],
    env: {
      HOME: process.env.HOME,
      PATH: '',
      PIP_NO_INDEX: '1',
      NODE_ENV: '',
      VID2NOTE_DATA_DIR: path.join(root, 'data'),
    },
    timeout: 60_000,
  })
  try {
    const page = await application.firstWindow({ timeout: 60_000 })
    await page.locator('body').waitFor({ state: 'visible' })
    assert.match(await page.locator('body').innerText(), /个人知识库/)
    const connection = await page.evaluate(() => window.electronAPI.getBackendConnection())
    const health = await fetch(`${connection.baseUrl}/api/v1/health`, {
      headers: { Authorization: `Bearer ${connection.token}` },
    })
    assert.equal(health.ok, true)
    const unauthenticated = await fetch(`${connection.baseUrl}/api/v1/config`)
    assert.equal(unauthenticated.status, 401)
    const authenticated = await fetch(`${connection.baseUrl}/api/v1/config`, {
      headers: { Authorization: `Bearer ${connection.token}` },
    })
    assert.equal(authenticated.ok, true)
  } finally {
    await application.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
