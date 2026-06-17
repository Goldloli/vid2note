const { test, expect } = require('@playwright/test')

test.describe('设置页', () => {
  test('设置页 Tab 渲染', async ({ page }) => {
    await page.goto('/#/settings')
    await expect(page.locator('.set-tabs')).toBeVisible()
    // Tab 按钮可见
    await expect(page.getByRole('button', { name: 'ASR 语音识别' })).toBeVisible()
    await expect(page.getByRole('button', { name: '保留策略' })).toBeVisible()
  })

  test('切换到保留策略 Tab 显示开关', async ({ page }) => {
    await page.goto('/#/settings')
    await page.getByRole('button', { name: '保留策略' }).click()
    await expect(page.getByText('保留原始视频')).toBeVisible()
    await expect(page.getByText('保留字幕 SRT')).toBeVisible()
  })
})
