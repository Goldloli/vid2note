const path = require('node:path')
const fs = require('node:fs')
const { execFileSync } = require('node:child_process')
const { _electron: electron, test, expect } = require('@playwright/test')

const ROOT = path.resolve(__dirname, '../../..')
const USER_DATA = path.join(process.env.VID2NOTE_E2E_DATA_DIR, 'electron-user-data')
const APP_DATA = path.join(process.env.VID2NOTE_E2E_DATA_DIR, 'electron-app-data')

async function launchApp() {
  const application = await electron.launch({
    args: ['.', `--user-data-dir=${USER_DATA}`],
    cwd: path.join(ROOT, 'desktop'),
    env: {
      ...process.env,
      NODE_ENV: 'development',
      VID2NOTE_RENDERER_URL: 'http://localhost:5174',
      VID2NOTE_VENV_PYTHON: path.join(ROOT, '.venv/bin/python'),
      PYTHONPATH: `${path.join(ROOT, 'core/src')}:${path.join(ROOT, 'server/src')}`,
      VID2NOTE_DATA_DIR: APP_DATA,
      VID2NOTE_OPEN_DEVTOOLS: '0',
    },
  })
  return { application, window: await application.firstWindow() }
}

async function quitApp(application) {
  await application.evaluate(({ app }) => app.quit())
  await application.close()
}

async function importSrt(window, text, expectedCount) {
  await window.goto('http://localhost:5174/#/workspace/import')
  await window.getByTestId('srt-input').setInputFiles({
    name: 'restart-topic.srt',
    mimeType: 'application/x-subrip',
    buffer: Buffer.from(text),
  })
  const tasks = window.locator('tbody tr').filter({ hasText: 'restart-topic.srt' })
  await expect(tasks).toHaveCount(expectedCount, { timeout: 20_000 })
  await expect(tasks.filter({ hasText: '已完成' })).toHaveCount(expectedCount, { timeout: 20_000 })
}

async function approve(window, summary) {
  await window.goto('http://localhost:5174/#/workspace/changesets')
  await window.getByRole('link', { name: new RegExp(summary) }).last().click()
  await window.getByTestId('approve-selected').click()
  const applied = window.locator('.changeset-list section').filter({ hasText: '已应用' })
  await expect(applied.getByRole('link', { name: new RegExp(summary) })).toBeVisible()
}

function attachFixtureVideo(sourceId) {
  const sourceDir = path.join(APP_DATA, 'vault', 'raw', sourceId)
  const original = path.join(sourceDir, 'original.mp4')
  execFileSync('ffmpeg', [
    '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
    'color=c=blue:s=320x180:r=30', '-t', '6', '-pix_fmt', 'yuv420p', original,
  ])
  const identityPath = path.join(sourceDir, 'source.yaml')
  const identity = fs.readFileSync(identityPath, 'utf8')
    .replace('original_available: false', 'original_available: true')
    .replace('original_relative_path: null', `original_relative_path: raw/${sourceId}/original.mp4`)
  fs.writeFileSync(identityPath, identity)
}

async function openCompiledPage(window) {
  await window.getByRole('link', { name: '知识库' }).click()
  await expect(window).toHaveURL(/#\/workspace\/wiki/)
  await window.getByPlaceholder('搜索页面和来源').fill('restart-topic.srt')
  await window.locator('.search-results small').filter({ hasText: 'wiki/' }).locator('..').click()
}

test('Electron restart preserves the complete two-source knowledge workflow', async () => {
  test.setTimeout(120_000)
  const first = await launchApp()
  await importSrt(first.window, '1\n00:00:01,000 --> 00:00:03,000\nRestart first evidence.\n', 1)
  await approve(first.window, 'Create compiled page')
  await importSrt(first.window, '1\n00:00:04,000 --> 00:00:06,000\nRestart second evidence.\n', 2)
  await approve(first.window, 'Enhance compiled page')

  await openCompiledPage(first.window)
  const evidence = first.window.locator('[data-evidence-source]')
  await expect(evidence).toHaveCount(2)
  await first.window.getByRole('button', { name: /附加当前页/ }).click()
  await first.window.getByPlaceholder('询问当前知识库…').fill('总结重启前的两个来源')
  await first.window.getByRole('button', { name: '发送' }).click()
  await expect(first.window.locator('[data-event-type="run.completed"]')).toBeVisible()

  const sourceId = await evidence.nth(1).getAttribute('data-evidence-source')
  expect(sourceId).toMatch(/^src_/)
  attachFixtureVideo(sourceId)
  await evidence.nth(1).click()
  await expect(first.window.getByText('Restart second evidence.')).toBeVisible()
  await expect(first.window.locator('video')).toBeVisible({ timeout: 20_000 })
  await quitApp(first.application)

  const restarted = await launchApp()
  try {
    await openCompiledPage(restarted.window)
    await expect(restarted.window.locator('[data-evidence-source]')).toHaveCount(2)
    await restarted.window.getByRole('link', { name: '变更审批' }).click()
    await expect(restarted.window.getByText('已应用').first()).toBeVisible()
    await restarted.window.getByRole('link', { name: 'Agent 会话' }).click()
    await restarted.window.getByRole('navigation', { name: '历史 Agent 会话' }).getByRole('button').first().click()
    await expect(restarted.window.locator('[data-event-type="run.completed"]').first()).toBeVisible()
    await expect(restarted.window.getByText('来源证据').first()).toBeVisible()
    await restarted.window.goto(`http://localhost:5174/#/workspace/sources/${sourceId}?start=4000&end=6000`)
    await expect(restarted.window.getByText('Restart second evidence.')).toBeVisible()
    await expect(restarted.window.locator('video')).toBeVisible({ timeout: 20_000 })
  } finally {
    await quitApp(restarted.application)
  }
})
