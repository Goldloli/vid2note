# open-source-distribution Specification

## Purpose

定义仓库公开分发前后的治理文件、凭据与隐私边界、依赖许可证门禁、质量验证和 GitHub 安全强化要求。

## Requirements

### Requirement: 开源治理文件完整

公开仓库 MUST 包含明确的开源许可证、第三方归属说明、中英文使用文档、贡献指南、行为准则、安全策略、更新日志以及 Issue/PR 模板。文档中的安装、端口、版本、发布和安全入口 MUST 与实际仓库状态一致。

#### Scenario: 执行公开发布预检

- **WHEN** 维护者准备把仓库切换为 Public
- **THEN** 所有治理文件和文档相对链接 MUST 存在，许可证与运行依赖的许可证边界 MUST 无冲突或未说明义务

### Requirement: 公开树不含凭据和个人环境路径

Git 跟踪文件 MUST NOT 包含真实 API Key、Cookie、主密钥、凭据密文、运行设置、任务数据或维护者个人绝对路径。发布预检 MUST 同时扫描当前树、全部本地 Git blob 和远端安全告警；扫描输出 MUST NOT 回显凭据原文。

#### Scenario: 当前凭据未进入历史

- **WHEN** 发布预检以内存中的实际本地凭据对全部 Git blob 做精确匹配
- **THEN** 结果 MUST 为零真实命中，报告 SHALL 只包含规则、文件、提交和不可逆短指纹

#### Scenario: 示例或测试夹具触发规则

- **WHEN** 模式扫描命中明确的测试夹具或空白示例配置
- **THEN** 维护者 SHALL 记录其为假阳性并证明它与实际凭据不一致，不得把所有模式命中直接视为安全

### Requirement: 依赖与许可证门禁

Python 和 Node 运行依赖 MUST 使用锁定版本，发布时 MUST 不含已知 High 或 Critical 漏洞。被打包进运行镜像的第三方依赖 MUST 与项目分发方式兼容，强 copyleft 或商业双许可依赖若未满足其义务 MUST 在发布前移除。

#### Scenario: 依赖审计发现高危漏洞

- **WHEN** `pip-audit` 或 `npm audit --audit-level=high` 返回命中
- **THEN** CI MUST 失败且版本标签和容器发布 MUST NOT 继续

#### Scenario: 运行依赖许可证不兼容

- **WHEN** 许可证审计发现未处理的 AGPL、SSPL、BUSL 或其他限制性运行依赖
- **THEN** 维护者 MUST 移除该依赖、满足并记录许可证义务或取得商业许可后才能发布

### Requirement: 公开发布质量门禁

公开前 MUST 通过后端测试、前端测试与构建、依赖审计、OpenSpec 严格校验、生产 Docker 镜像构建和密钥复扫。任何必要门禁失败时仓库 MUST 保持 Private，版本标签 MUST NOT 创建。

#### Scenario: 任一门禁失败

- **WHEN** 发布检查中的任一必需任务失败或被意外跳过
- **THEN** 发布流程 MUST 停止并保留可定位的失败原因

#### Scenario: 全部门禁通过

- **WHEN** 所有本地和 Private 阶段门禁成功且所有者确认隐私选择
- **THEN** 仓库 MAY 切换为 Public，并 SHALL 进入公开后的 GitHub 安全强化步骤

### Requirement: GitHub 公共仓库安全强化

仓库公开后 MUST 启用 Secret Scanning、Push Protection、Dependabot alerts、Code Scanning、私密漏洞报告和 `main` 分支保护。CodeQL、Secret Scanning 和 Dependabot MUST 至少完成一次成功运行或无告警确认，之后才能发布首个公共版本。

#### Scenario: 仓库刚切换为 Public

- **WHEN** GitHub 可见性变为 Public
- **THEN** 维护者 SHALL 立即开启安全功能、配置 `main` 保护并重新运行 CI 与 CodeQL

#### Scenario: GitHub 安全扫描发现真实凭据

- **WHEN** Secret Scanning 报告可用凭据
- **THEN** 维护者 MUST 先撤销或轮换凭据，再按 GitHub 敏感数据流程清理历史并关闭告警
