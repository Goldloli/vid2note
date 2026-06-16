# E2E 测试（Playwright）

## 运行

```bash
cd desktop
npm install                # 安装含 @playwright/test
npx playwright install     # 安装浏览器（首次）
VID2NOTE_E2E_DATA_DIR=/tmp/vid2note-e2e npm run test:e2e
```

## 策略（设计稿 11.4）

- **不依赖外部网络**：后端为真实 FastAPI（`webServer` 自动拉起），前端为 Vite dev server。
- 后端 worker 默认使用真实 pipeline 节点链路；下载/ASR/LLM 在缺失外部依赖（API Key、模型、二进制）时会回退到 mock，因此 E2E 在无密钥环境也能跑通任务创建与列表展示。
- **数据隔离**：通过 `VID2NOTE_E2E_DATA_DIR` 环境变量把 DB 与产物指向临时目录。
- 标记 `@slow` 的本地 ASR 完整跑通用例放 `test_local_asr.spec.js`（nightly，CI 默认跳过）。

## 文件

- `test_home_loads.spec.js` —— 首页渲染、标题、输入框
- `test_url_input.spec.js` —— URL 输入 → 任务创建 → 列表显示
- `test_health.spec.js` —— 后端健康检查与模型列表
- `fixtures/` —— 测试夹具（sample SRT 等）
