// E2E: URL 输入（自研回执设计系统）
const { test, expect } = require('@playwright/test')

test.describe('URL 输入', () => {
  test('有效 URL 提交后任务出现在进行中', async ({ page }) => {
    await page.goto('/')
    const input = page.locator('.input-affix input')
    await input.fill('https://example.com/test-video')
    await page.locator('.input-affix button[type="submit"]').click()
    // 进行中区域出现任务卡（含 pipeline-rail）
    await expect(page.locator('.pipeline-rail')).toBeVisible({ timeout: 15_000 })
  })

  test('无效 URL 显示错误', async ({ page }) => {
    await page.goto('/')
    await page.locator('.input-affix input').fill('not-a-valid-url')
    await page.locator('.input-affix button[type="submit"]').click()
    await expect(page.locator('.input-affix + p')).toContainText(/URL|http/i)
  })
})
