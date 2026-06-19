// Playwright 配置：vid2note 桌面端 E2E
//
// 策略（设计稿 11.4）：
//   - 不依赖外部网络：本地启动 FastAPI 后端 + Vite 前端
//   - 后端 worker 用真实节点链路，但下载器/ASR/LLM 用桩（mock），
//     通过环境变量注入，避免真实下载/识别
//   - DB / 上传目录隔离到临时目录
const path = require('path')
const fs = require('fs')

const FRONT_PORT = process.env.VID2NOTE_E2E_FRONT_PORT || 5174
const BACK_PORT = process.env.VID2NOTE_E2E_BACK_PORT || 18765
// 优先用仓库 venv 的 python（已装好 vid2note 依赖），否则系统 python
const ROOT = path.resolve(__dirname, '..')
const PY = process.env.VID2NOTE_E2E_PYTHON || (fs.existsSync(path.join(ROOT, '.venv', 'bin', 'python')) ? path.join(ROOT, '.venv', 'bin', 'python') : 'python')
const SYSTEM_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// defineConfig 是可选的类型辅助；不 import 以避免全局/本地 playwright 版本冲突
/** @type {import('@playwright/test').PlaywrightTestConfig} */
const config = {
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${FRONT_PORT}`,
    trace: 'on-first-retry',
    actionTimeout: 10_000,
    launchOptions: fs.existsSync(SYSTEM_CHROME) ? { executablePath: SYSTEM_CHROME } : undefined,
  },
  webServer: [
    {
      // 后端：真实 FastAPI，数据隔离到临时目录，关闭 worker 自动启动避免污染
      command: `${PY} -m uvicorn vid2note_server.main:app --host 127.0.0.1 --port ${BACK_PORT}`,
      port: BACK_PORT,
      timeout: 30_000,
      cwd: ROOT,
      env: {
        VID2NOTE_DATA_DIR: process.env.VID2NOTE_E2E_DATA_DIR || '/tmp/vid2note-e2e',
        VID2NOTE_RUN_MODE: 'dev',
      },
      reuseExistingServer: true,
    },
    {
      // 前端：Vite dev server，API 指向后端
      command: `VITE_API_BASE_URL=http://localhost:${BACK_PORT}/api/v1 npx vite --port ${FRONT_PORT} --strictPort`,
      port: FRONT_PORT,
      timeout: 30_000,
      reuseExistingServer: true,
    },
  ],
}

module.exports = config
