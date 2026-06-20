const { test, expect } = require('@playwright/test')

test('keyboard navigation covers the tree, drawer and diff selection', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/workspace/wiki')

  const firstTreeItem = page.getByRole('treeitem').first()
  await firstTreeItem.focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('treeitem').nth(1)).toBeFocused()

  await page.setViewportSize({ width: 820, height: 800 })
  await expect(page.getByTestId('agent-panel')).toHaveClass(/is-drawer/)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('agent-panel')).toHaveAttribute('aria-hidden', 'true')
  await page.getByRole('button', { name: '切换 Agent 面板' }).click()
  await expect(page.getByTestId('agent-panel')).toHaveAttribute('aria-hidden', 'false')

  await page.goto('/#/workspace/import')
  await page.getByTestId('srt-input').setInputFiles({
    name: 'accessibility-review.srt',
    mimeType: 'application/x-subrip',
    buffer: Buffer.from('1\n00:00:01,000 --> 00:00:02,000\nKeyboard review evidence.\n'),
  })
  const imported = page.locator('tbody tr').filter({ hasText: 'accessibility-review.srt' })
  await expect(imported).toContainText('已完成', { timeout: 20_000 })
  await page.goto('/#/workspace/changesets')
  await page.getByRole('link', { name: /Create compiled page/ }).last().click()
  const operation = page.locator('[data-operation-index="0"] input')
  await operation.focus()
  await page.keyboard.press('Space')
  await expect(operation).not.toBeChecked()

  for (const button of await page.getByRole('button').all()) {
    await expect(button).toHaveAccessibleName(/.+/)
  }
})
