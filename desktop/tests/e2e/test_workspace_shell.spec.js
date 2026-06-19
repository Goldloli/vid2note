const { test, expect } = require('@playwright/test')

test('legacy video workflow runs inside one workspace shell', async ({ page }) => {
  await page.goto('/#/workspace/import')

  await expect(page.getByRole('navigation', { name: '主工具' })).toBeVisible()
  await expect(page.getByTestId('workspace-main')).toBeVisible()
  await expect(page.getByRole('heading', { name: '导入与处理' })).toBeVisible()
  await expect(page.getByTestId('srt-input')).toBeAttached()

  await page.getByRole('link', { name: '设置' }).click()
  await expect(page).toHaveURL(/workspace\/settings/)
  await expect(page.getByRole('navigation', { name: '主工具' })).toBeVisible()
})

test('workspace shell follows responsive breakpoints', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/workspace/import')
  await expect(page.getByTestId('workspace-tree')).toHaveAttribute('aria-hidden', 'false')
  await expect(page.getByTestId('agent-panel')).not.toHaveClass(/is-drawer/)

  await page.setViewportSize({ width: 1024, height: 800 })
  await expect(page.getByTestId('workspace-tree')).toHaveAttribute('aria-hidden', 'true')

  await page.setViewportSize({ width: 820, height: 800 })
  await expect(page.getByTestId('agent-panel')).toHaveClass(/is-drawer/)
})

test('keyboard can reach the rail and panel controls', async ({ page }) => {
  await page.goto('/#/workspace/import')
  await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur())

  const labels = []
  for (let index = 0; index < 12; index += 1) {
    await page.keyboard.press('Tab')
    labels.push(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')))
  }

  expect(labels).toContain('vid2note 工作台')
  expect(labels).toContain('切换文件树')
  expect(labels).toContain('切换 Agent 面板')
})
