// E2E: URL 输入 → 任务创建
// 验证输入视频链接后任务出现在任务列表（后端真实处理，worker 用真实节点链路）
const { test, expect } = require('@playwright/test')

test.describe('URL 输入', () => {
  test('有效 URL 提交后任务出现在列表', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('input')
    await input.fill('https://example.com/test-video')

    // 点击"开始"按钮
    await page.getByRole('button', { name: /开始/ }).click()

    // 任务列表应出现一个任务条目（含 task_ 前缀的 id）
    const taskItem = page.locator('.task-item')
    await expect(taskItem).toBeVisible({ timeout: 15_000 })
    await expect(taskItem.locator('.task-id')).toContainText(/task_/)
  })

  test('无效 URL 显示错误提示', async ({ page }) => {
    await page.goto('/')

    const input = page.locator('input')
    await input.fill('not-a-valid-url')
    await page.getByRole('button', { name: /开始/ }).click()

    // 前端校验：显示错误提示
    await expect(page.locator('.error')).toBeVisible()
    await expect(page.locator('.error')).toContainText(/URL|http/i)
  })
})
