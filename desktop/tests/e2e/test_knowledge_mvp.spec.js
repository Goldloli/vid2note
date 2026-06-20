const { test, expect } = require('@playwright/test')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const API = 'http://127.0.0.1:18765/api/v1'

async function importSrt(page, text, completedCount) {
  await page.goto('/#/workspace/import')
  await page.getByTestId('srt-input').setInputFiles({
    name: 'shared-topic.srt',
    mimeType: 'application/x-subrip',
    buffer: Buffer.from(text),
  })
  await expect(page.locator('tbody tr')).toHaveCount(completedCount, { timeout: 20_000 })
}

async function approvePending(page, request, summary) {
  await page.goto('/#/workspace/changesets')
  await page.getByRole('link', { name: new RegExp(summary) }).click()
  await page.getByTestId('approve-selected').click()
  await expect.poll(async () => {
    const response = await request.get(`${API}/changesets`, { params: { status: 'applied' } })
    return (await response.json()).filter((item) => item.summary.includes(summary)).length
  }).toBe(1)
}

function attachFixtureVideo(sourceId) {
  const sourceDir = path.join(process.env.VID2NOTE_E2E_DATA_DIR, 'vault', 'raw', sourceId)
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

test('two sources enhance one Wiki page and remain usable through review, Agent and evidence UI', async ({ page, request }) => {
  await importSrt(page, '1\n00:00:01,000 --> 00:00:03,000\nFirst evidence.\n', 1)
  await approvePending(page, request, 'Create compiled page')

  await importSrt(page, '1\n00:00:04,000 --> 00:00:06,000\nSecond evidence.\n', 2)
  await approvePending(page, request, 'Enhance compiled page')

  const applied = await (await request.get(`${API}/changesets`, { params: { status: 'applied' } })).json()
  const create = applied.find((item) => item.summary.includes('Create compiled page'))
  const enhance = applied.find((item) => item.summary.includes('Enhance compiled page'))
  expect(enhance.operations[0].path).toBe(create.operations[0].path)

  await page.goto(`/#/workspace/wiki?path=${encodeURIComponent(create.operations[0].path)}`)
  const evidence = page.locator('[data-evidence-source]')
  await expect(evidence).toHaveCount(2)

  await page.getByRole('button', { name: /附加当前页/ }).click()
  await page.getByPlaceholder('询问当前知识库…').fill('总结已审批的证据')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.locator('[data-event-type="message.delta"]')).toContainText('来源证据')
  await expect(page.locator('[data-event-type="run.completed"]')).toBeVisible()

  const sourceId = await evidence.nth(1).getAttribute('data-evidence-source')
  expect(sourceId).toMatch(/^src_/)
  attachFixtureVideo(sourceId)
  await evidence.nth(1).click()
  await expect(page).toHaveURL(new RegExp(`/workspace/sources/${sourceId}.*start=4000.*end=6000`))
  await expect(page.getByText('Second evidence.')).toBeVisible()
  const video = page.locator('video')
  await expect(video).toBeVisible({ timeout: 20_000 })
  await video.evaluate((element) => new Promise((resolve) => {
    if (element.readyState >= HTMLMediaElement.HAVE_METADATA) resolve()
    else element.addEventListener('loadedmetadata', resolve, { once: true })
  }))
  const clip = await (await request.get(`${API}/media/clip`, {
    params: { source_id: sourceId, start_ms: 4000, end_ms: 6000 },
  })).json()
  const absolutePlaybackMs = await video.evaluate((element) => element.currentTime * 1000) + clip.rendered_start_ms
  expect(Math.abs(absolutePlaybackMs - 4000)).toBeLessThanOrEqual(2000)

  await page.reload()
  await expect(page.getByText('Second evidence.')).toBeVisible()
  const persisted = await (await request.get(`${API}/vault/page`, { params: { path: create.operations[0].path } })).json()
  expect(persisted.content).toContain(create.source_ids[0])
  expect(persisted.content).toContain(enhance.source_ids[0])
})
