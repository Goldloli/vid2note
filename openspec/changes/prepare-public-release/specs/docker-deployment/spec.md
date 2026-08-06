## MODIFIED Requirements

### Requirement: 自动构建与发布

Pull Request MUST 运行后端测试与依赖审计、前端检查与依赖审计，并在这些任务成功后构建生产镜像。版本标签只有在同一提交通过全部质量门禁、许可证检查、密钥复扫和公开仓库安全检查后才 SHALL 触发 amd64/arm64 镜像发布到 GHCR，并生成构建来源证明。

#### Scenario: Pull Request 验证

- **WHEN** Pull Request 指向 `main`
- **THEN** CI SHALL 运行后端测试、`pip-audit`、前端 check、`npm audit --audit-level=high` 和生产镜像构建，任一失败 SHALL 阻止合并

#### Scenario: 私有仓库 CodeQL 权限不可用

- **WHEN** GitHub 个人 Private 仓库不允许上传 CodeQL 结果
- **THEN** workflow SHALL 明确跳过 CodeQL 分析而不是产生误导性失败，并 SHALL 在仓库公开后自动恢复分析

#### Scenario: 推送版本标签

- **WHEN** 维护者在全部发布门禁通过的公开提交上推送 `v*` 标签
- **THEN** GitHub Actions SHALL 发布语义化标签和 `latest` 镜像，并 SHALL 附带构建来源证明
