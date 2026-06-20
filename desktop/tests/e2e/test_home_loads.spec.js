const { test, expect } = require('@playwright/test')

test.describe('首页加载', () => {
  test('标题栏 + 输入框 + 侧栏渲染', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.titlebar')).toBeVisible()
    await expect(page.locator('.titlebar')).toContainText('vid2note')
    await expect(page.locator('.input-affix input')).toBeVisible()
    await expect(page.getByRole('navigation', { name: '主工具' })).toBeVisible()
    await expect(page.getByTestId('workspace-tree')).toBeVisible()
  })

  test('统计卡 + composer 区域', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('新建任务', { exact: true })).toBeVisible()
    await expect(page.locator('.stat').first()).toBeVisible()
  })
})
