## Context

vid2note 当前是个人账户下的 Private 仓库，应用边界仍是无登录的 localhost 单用户工具。开源治理文档和安全默认已经存在，但发布审计发现四类问题：CI 把手工 Playwright 脚本当成 pytest 模块收集；Python/Node 依赖有已知漏洞；稳定 PDF 能力仍携带 PyMuPDF 的 AGPL 运行依赖；若干历史设计文档包含个人绝对路径。GitHub Secret Scanning、Dependabot alerts 和 Code Scanning 在当前私有个人仓库中不可用，必须在公开后立即开启并复跑。

当前真实 DeepSeek 凭据仅存在于被忽略的 `.env` 和 Fernet 凭据仓库中，精确扫描未在 Git 对象中命中。测试夹具里的 `sk-...` 已通过 DeepSeek 官方 `/models` 鉴权端点确认返回 401，不是真实凭据。

## Goals / Non-Goals

**Goals:**

- 让本地、CI 和公开后的 GitHub 安全检查形成一致且可重复的发布门禁。
- 清除已知高危依赖和 PyMuPDF/AGPL 分发风险，同时保持现有 PDF 文本参考能力。
- 确保公开树不含真实凭据、运行数据、个人绝对路径或误导性的发布信息。
- 公开后启用 Secret Scanning、Push Protection、Dependabot、CodeQL、私密漏洞报告和 `main` 保护。

**Non-Goals:**

- 不把本地单用户应用改造成公网服务。
- 不改变 ASR、LLM、笔记质量或成本策略。
- 不引入 OCR，也不扩大 PDF 功能范围。
- 未经仓库所有者明确确认，不重写 Git 作者邮箱历史、不清理不可达对象、不切换仓库可见性。

## Decisions

### D1：保留 `PDFParser` 门面，内部统一使用 pypdf

`PDFParser` 的公开方法和返回结构保持不变，底层以 `pypdf.PdfReader` 提取分页文本、章节标题和大纲；图片列表在基础模式中保持为空。这样既保留内核门面兼容性，又能删除 PyMuPDF 运行依赖。备选方案是彻底删除遗留解析器，但会扩大门面和测试改动；购买 PyMuPDF 商业许可或把整体改为 AGPL 与当前 MIT 发布目标不符。

### D2：依赖门禁以“无已知 High/Critical”为最低线

Python 运行依赖升级到 `pip-audit` 无命中版本；Node 锁文件通过最小升级消除 `npm audit --audit-level=high` 命中。锁文件必须随变更提交，Docker 继续使用锁定版本构建。许可证检查同时确认运行依赖不存在未说明的强 copyleft 包。

### D3：把单元测试和手工 E2E 的依赖边界分开

Playwright 脚本继续保留为显式执行的端到端入口，但模块导入不再要求默认开发环境预装 Playwright；CI 的普通 pytest 只运行可隔离测试。E2E 依赖放到独立清单，并在文档中给出显式安装和执行命令。备选方案是把 Playwright 加进所有开发环境，但会增加安装体积且 CI 并不运行浏览器场景。

### D4：采用“私有预检 → 公开后强化”的两阶段发布

私有阶段必须先让后端测试、前端 check、两端依赖审计、OpenSpec 校验和 Docker 构建通过。CodeQL 在个人 Private 仓库中不具备上传权限时跳过分析任务，避免把平台权限限制伪装成代码失败。公开后立即启用 GitHub 安全功能并重新触发 CodeQL；只有公开阶段检查通过才创建首个版本标签和 GHCR 镜像。

### D5：密钥校验采用真实值精确匹配与模式扫描双层检查

发布前从本机 `.env` 和加密凭据仓库只在内存中取得值，对全部本地 Git blob 做精确匹配；再用 provider、GitHub、AWS、Google、Slack 和私钥头等模式扫描。报告只输出路径、提交和 SHA-256 短指纹，不输出凭据原文。GitHub 公开后再用 Secret Scanning 覆盖远端完整历史。

### D6：隐私清理区分工作树和 Git 历史

工作树中的 `/Users/...`、`/Volumes/...` 替换为 `<repo>`、`<workspace>` 等通用路径。提交作者 Gmail 属于历史元数据；若所有者不接受公开，需单独确认 noreply 地址后执行全历史重写和强制推送，该操作不与普通代码修复混在一起。

## Risks / Trade-offs

- [pypdf 对复杂 PDF 的文本顺序可能与 PyMuPDF 不同] → 用多页、标题、空文本、损坏和加密 PDF 回归测试锁定稳定边界；扫描件仍明确不承诺 OCR。
- [依赖升级可能引入兼容变化] → 先升级最小必要版本，运行 443 项后端测试、前端完整门禁和 Docker 构建。
- [Private 阶段跳过 CodeQL 会减少一次静态分析] → 公开后立即启用并强制复跑，未成功前不打版本标签。
- [公开后 GitHub 自动扫描可能发现本地规则未识别的模式] → 预留处理窗口；真实命中先撤销凭据，再清理历史。
- [历史邮箱重写会改变全部提交 SHA] → 默认不执行，必须得到所有者明确授权并在公开前完成。

## Migration Plan

1. 增加 PDFParser 的 pypdf 回归测试，确认旧实现基线后替换底层并移除 PyMuPDF。
2. 升级 Python/Node 依赖并修正 pytest/E2E 边界，执行局部测试和依赖审计。
3. 清理隐私路径、校正文档和 GitHub workflow，执行全量后端、前端、OpenSpec 和 Docker 门禁。
4. 再次执行当前凭据精确扫描和通用密钥模式扫描。
5. 所有者确认历史邮箱与仓库可见性后，完成必要的历史处理、提交和推送。
6. 将仓库切换为 Public，启用安全功能与分支保护，复跑 CI/CodeQL/Secret Scanning；全部通过后再发布 `v1.0.0`。

回滚时可恢复依赖锁文件和 PDFParser 实现；公开可见性、历史重写和凭据撤销属于外部状态操作，必须单独记录并在执行前再次核对目标。

## Resolved Questions

- 所有者确认使用 `39011904+Goldloli@users.noreply.github.com` 改写 `main` 的 146 个历史提交，并接受 8 个 GitHub 托管的关闭 PR 引用仍可能保留旧 Gmail 元数据。
- 所有者确认由本次任务直接把仓库切换为 Public，并继续完成安全强化和首个版本发布。
