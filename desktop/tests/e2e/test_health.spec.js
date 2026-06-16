// E2E: 后端健康检查
// 验证 webServer 启动的 FastAPI 后端可达，且 /api/v1/health 端点正确响应
const { test, expect } = require('@playwright/test')

const BACK_PORT = process.env.VID2NOTE_E2E_BACK_PORT || 18765

test.describe('后端健康检查', () => {
  test('/api/v1/health 返回 ok', async ({ request }) => {
    const resp = await request.get(`http://localhost:${BACK_PORT}/api/v1/health`)
    expect(resp.ok()).toBeTruthy()
    const data = await resp.json()
    expect(data.status).toBe('ok')
  })

  test('前端通过代理或直连能访问后端模型列表', async ({ request }) => {
    const resp = await request.get(`http://localhost:${BACK_PORT}/api/v1/models`)
    expect(resp.ok()).toBeTruthy()
    const data = await resp.json()
    expect(data.llm_providers).toContain('qwen')
    expect(data.asr_providers).toContain('funasr')
  })
})
