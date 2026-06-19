const fs = require('node:fs/promises')
const path = require('node:path')
const { test, expect } = require('@playwright/test')

test('本地 SRT 经真实 Worker 生成并导出来源笔记', async ({ page }) => {
  await page.goto('/#/workspace/import')
  await page.getByTestId('srt-input').setInputFiles(
    path.join(__dirname, 'fixtures', 'sample.srt')
  )

  const completed = page.locator('tbody tr').filter({ hasText: '已完成' }).first()
  await expect(completed).toBeVisible({ timeout: 15_000 })
  const detailLink = completed.getByRole('link', { name: '详情' })
  const taskId = (await detailLink.getAttribute('href')).split('/').pop()
  await detailLink.click()

  await page.getByRole('button', { name: '笔记预览' }).click()
  await expect(page.locator('.note-pre')).toContainText('# 来源笔记')
  await expect(page.locator('.note-pre')).toContainText('证据：00:00:00–00:00:02')

  await page.goto(`/#/note/${taskId}`)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 .md' }).click()
  const download = await downloadPromise
  const markdown = await fs.readFile(await download.path(), 'utf-8')
  expect(markdown).toContain('vid2note 把视频转成 Markdown 笔记')
})
