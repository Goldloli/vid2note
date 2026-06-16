// E2E: 设置页
// 验证 /settings 页面渲染（LLM/ASR 提供商、保留策略、Cookie 管理区域）
const { test, expect } = require('@playwright/test')

test.describe('设置页', () => {
  test('设置页各区域渲染', async ({ page }) => {
    await page.goto('/#/settings')

    // 四个配置区块标题
    await expect(page.getByText('LLM 大模型')).toBeVisible()
    await expect(page.getByText('ASR 语音识别')).toBeVisible()
    await expect(page.getByText('Cookie 管理')).toBeVisible()
    await expect(page.getByText('保留策略')).toBeVisible()
  })

  test('保留策略开关存在', async ({ page }) => {
    await page.goto('/#/settings')
    await expect(page.getByText('保留视频文件')).toBeVisible()
    await expect(page.getByText('保留 SRT 字幕')).toBeVisible()
  })
})
