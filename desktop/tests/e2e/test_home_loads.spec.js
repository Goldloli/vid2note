// E2E: 首页加载
// 验证 Vite 前端启动后渲染 vid2note 标题与 URL 输入框
const { test, expect } = require('@playwright/test')

test.describe('首页加载', () => {
  test('显示标题与输入框', async ({ page }) => {
    await page.goto('/')
    // 标题
    await expect(page.locator('h1')).toHaveText(/vid2note/i)
    // URL 输入框存在
    await expect(page.locator('input')).toBeVisible()
  })

  test('任务列表区域存在', async ({ page }) => {
    await page.goto('/')
    // 任务列表卡片（el-card 头部含"任务列表"）
    await expect(page.getByText('任务列表')).toBeVisible()
  })
})
