const { test, expect } = require('@playwright/test')

test('workspace preserves pane preferences across all supported breakpoints', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/workspace/import')
  await expect(page.getByTestId('workspace-tree')).toHaveAttribute('aria-hidden', 'false')
  await expect(page.getByTestId('agent-panel')).not.toHaveClass(/is-drawer/)

  const treeResize = page.getByRole('separator', { name: '调整文件树宽度' })
  const before = Number(await treeResize.getAttribute('aria-valuenow'))
  await treeResize.focus()
  await page.keyboard.press('ArrowRight')
  await expect(treeResize).toHaveAttribute('aria-valuenow', String(before + 10))
  await page.reload()
  await expect(page.getByRole('separator', { name: '调整文件树宽度' })).toHaveAttribute('aria-valuenow', String(before + 10))

  await page.setViewportSize({ width: 1024, height: 800 })
  await expect(page.getByTestId('workspace-tree')).toHaveAttribute('aria-hidden', 'true')
  await page.getByRole('button', { name: '切换文件树' }).click()
  await expect(page.getByTestId('workspace-tree')).toHaveAttribute('aria-hidden', 'false')

  await page.setViewportSize({ width: 820, height: 800 })
  await expect(page.getByTestId('agent-panel')).toHaveClass(/is-drawer/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
