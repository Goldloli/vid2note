## 1. 骨架与安全基线

- [x] 1.1 为开源发布预检增加密钥假阳性、敏感路径和许可证/依赖门禁的可重复测试或脚本
- [x] 1.2 验证测试夹具 Key 的 DeepSeek 鉴权状态，只记录状态与指纹且不产生模型费用

## 2. PDF 与后端依赖

- [x] 2.1 先补充 `PDFParser` 的多页文本、章节、大纲、空文本、损坏与加密文件回归测试
- [x] 2.2 保持 `PDFParser` 门面并改用 `pypdf`，删除 `fitz` 引用和 PyMuPDF 运行依赖
- [x] 2.3 升级 `cryptography` 到无已知审计命中的版本并验证凭据加解密测试

## 3. 前端与 CI

- [x] 3.1 修正 Playwright 手工 E2E 与普通 pytest 的导入/依赖边界，并记录独立安装方式
- [x] 3.2 最小升级前端锁文件以消除 High/Critical npm audit 命中
- [x] 3.3 调整 CI/CodeQL：测试和审计成功后构建镜像，Private 阶段不因 CodeQL 上传权限产生伪失败

## 4. 文档、设置与发布元数据

- [x] 4.1 清理全部已跟踪文档中的 `/Users/...`、`/Volumes/...` 个人绝对路径并增加复扫门禁
- [x] 4.2 校正 README、SECURITY、NOTICE、CHANGELOG、E2E 和发布说明，使能力、许可证与 GitHub 状态一致
- [x] 4.3 核对 `.gitignore`、`.dockerignore`、示例环境变量和凭据存储，确保运行配置与真实凭据不进入 Git

## 5. 全量验证与公开发布

- [x] 5.1 运行后端全量测试、前端 check、pip/npm 审计、OpenSpec strict validate、生产 Docker 构建和完整密钥复扫
- [ ] 5.2 由所有者确认是否接受历史 Gmail；若不接受，确认 noreply 地址后单独重写历史并复验远端
- [ ] 5.3 所有者确认后提交并推送修复，将仓库切换为 Public，启用 GitHub 安全功能与 `main` 保护
- [ ] 5.4 复跑 GitHub CI、CodeQL、Secret Scanning 和 Dependabot；全部通过后创建 `v1.0.0` 标签与 GHCR 发布
- [ ] 5.5 同步主规格、严格校验并归档 `prepare-public-release` change
