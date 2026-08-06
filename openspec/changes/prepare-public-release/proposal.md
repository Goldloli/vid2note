## Why

仓库已经具备基础开源治理文件，但当前 `main` 的 CI、依赖审计、许可证边界和隐私清理尚未达到可公开发布标准。现在需要先形成可重复验证的发布门禁，再将仓库从 Private 切换为 Public，避免把已知漏洞、AGPL 运行依赖或个人环境信息带入首个公开版本。

## What Changes

- 将 PDF 基础文本提取从 PyMuPDF 统一为现有的 `pypdf`，删除未被稳定流水线使用的遗留 `fitz` 解析器和 AGPL 运行依赖。
- 升级 Python `cryptography` 和前端间接依赖，确保 `pip-audit` 与 `npm audit --audit-level=high` 无已知漏洞。
- 修正 GitHub Actions 测试边界：普通 pytest 不误收集需独立环境的 Playwright E2E，前后端测试、审计和生产镜像构建全部通过。
- 清理已跟踪文档中的个人绝对路径，校正文档、版本标签与安全报告入口，避免开源后泄漏本机环境或指向不存在的能力。
- 建立开源发布门禁：许可证与第三方归属明确、当前树和 Git 历史密钥扫描无真实命中、GitHub 安全功能开启、`main` 保护规则生效后才允许公开发布。
- 保留本地单用户、localhost 默认绑定和加密凭据边界；公开的是源代码和构建产物，不把应用变成公网多用户服务。

## Capabilities

### New Capabilities

- `open-source-distribution`: 定义公开仓库的许可证、隐私、依赖安全、CI、密钥扫描、漏洞报告和发布门禁。

### Modified Capabilities

- `pdf-reference`: 基础 PDF 文本和章节提取改用宽松许可证的 `pypdf`，不再要求 PyMuPDF。
- `docker-deployment`: PR/标签发布增加测试、依赖审计与生产镜像构建前置门禁，禁止带已知高危漏洞或不兼容许可证的运行依赖发布。

## Impact

- 后端：`backend/src/parsers/pdf_parser.py`、PDF 解析调用链、Python 依赖清单与相关测试。
- 前端：`package-lock.json` 中的受影响间接依赖。
- CI/CD：`.github/workflows/ci.yml`、CodeQL 与发布工作流的权限和门禁。
- 文档与仓库元数据：README、CHANGELOG、SECURITY、NOTICE、OpenSpec 历史文档中的本机路径，以及 GitHub 安全设置。
- 复用边界：继续复用 `ai_srt2md` 的字幕、LLM、Prompt、笔记和导图内核；本次只替换其遗留 PDF 解析依赖并补齐发布工程，不重写核心笔记流水线。

## Non-goals

- 不新增登录、远程部署、多用户、TLS 或公网访问能力。
- 不改变笔记档位、LLM Prompt、ASR 策略或任务数据格式。
- 不在本 change 中引入 OCR/MinerU 稳定能力，也不为扫描版 PDF 承诺文本识别。
- 不自动重写全部 Git 提交作者邮箱；是否清洗历史邮箱由仓库所有者单独确认。
