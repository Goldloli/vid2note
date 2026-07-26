# pdf-reference Specification

## Purpose
TBD - created by archiving change build-vid2note-v1. Update Purpose after archive.
## Requirements
### Requirement: PDF 讲义作为可选输入与视频任务配对

系统 MUST 支持在创建视频任务时附带一份可选的 PDF 讲义文件,该 PDF SHALL 与该视频任务一一配对,作为笔记生成阶段的参考材料。未附带 PDF 时,流水线 SHALL 正常运行且笔记生成不得因此失败或降级。每次任务 MUST 限定至多一份配对 PDF(对应「讲义对照」语义),超出 SHALL 被拒绝。

#### Scenario: 仅提供视频链接不附带 PDF

- **WHEN** 用户提交视频链接创建任务且未上传任何 PDF
- **THEN** 系统 SHALL 接受任务并正常运行六步流水线,笔记生成阶段 SHALL 在无 PDF 参考材料的情况下完成,不得因缺少 PDF 报错

#### Scenario: 视频任务附带一份 PDF 讲义

- **WHEN** 用户提交视频链接并同时上传一份 PDF 文件
- **THEN** 系统 SHALL 保存该 PDF 文件,将其记录为该任务的配对讲义,并在笔记生成阶段携带该 PDF 的解析内容作为参考材料

#### Scenario: 上传非 PDF 文件被拒绝

- **WHEN** 用户在 PDF 讲义入口上传了非 PDF 文件(如 .docx / .png / .epub)
- **THEN** 系统 SHALL 拒绝该文件,向用户返回明确的格式错误提示,且不得将其作为讲义配对到任务

#### Scenario: 同一任务附带多份 PDF 被拒绝

- **WHEN** 用户尝试为同一任务上传第二份 PDF 讲义
- **THEN** 系统 SHALL 拒绝并提示每次任务仅支持一份讲义,不得替换或累积

### Requirement: PDF 处理方案可配置

系统 MUST 提供两种 PDF 处理方案并在设置中可选:① 简单文本提取(pypdf)② MinerU 版面结构化拆解。默认方案 SHALL 为简单文本提取(因 MinerU 依赖较重)。方案切换 MUST 仅作用于切换后新建的任务,不得回溯重跑历史任务的已解析结果。

#### Scenario: 默认方案为简单文本提取

- **WHEN** 用户从未修改 PDF 处理方案设置而创建带 PDF 的任务
- **THEN** 系统 SHALL 使用简单文本提取(pypdf)方案解析该 PDF

#### Scenario: 设置切换为 MinerU 版面拆解

- **WHEN** 用户在设置页将 PDF 处理方案切换为「MinerU 版面结构化拆解」后新建带 PDF 的任务
- **THEN** 系统 SHALL 使用 MinerU 方案解析该任务的 PDF

#### Scenario: 方案切换不影响已存在任务

- **WHEN** 用户在已有任务 A(已完成 PDF 解析)之后将方案从 pypdf 切换为 MinerU,再新建任务 B
- **THEN** 系统 SHALL 仅对任务 B 应用 MinerU 方案,任务 A 的既有解析结果 MUST NOT 被自动重跑或覆盖

### Requirement: 简单文本提取方案

简单文本提取方案 MUST 使用 pypdf 从 PDF 提取纯文本,并 SHALL 识别讲义的章节结构(如「第X章」「第X节」、数字编号「1. / 1.1」、中文编号「一、二、」)。提取结果 SHALL 包含全文文本与检测到的章节大纲,供笔记生成阶段引用。

#### Scenario: 提取含章节结构的讲义

- **WHEN** 简单文本提取方案解析一份包含「第一章 / 1.1 / 一、」等标题的讲义 PDF
- **THEN** 系统 SHALL 输出该 PDF 的全文文本,并 SHALL 输出检测到的章节大纲(含标题文本、层级与所在页码)

#### Scenario: 提取扫描版无文字层 PDF

- **WHEN** 简单文本提取方案解析一份扫描版(无可提取文字层)的 PDF
- **THEN** 系统 SHALL 提取到空文本或极少文本,并 MUST 在解析结果中标记该 PDF 为「无可提取文字 / 低质量」,供后续决策参考

### Requirement: MinerU 版面结构化拆解方案

MinerU 方案 MUST 对 PDF 做版面结构化拆解:数学公式 SHALL 转换为 LaTeX,表格 SHALL 转换为 HTML,版面阅读顺序 SHALL 被还原。输出 SHALL 为带结构化元素的可读 Markdown,供笔记生成阶段按讲义版面引用。

#### Scenario: 公式转换为 LaTeX

- **WHEN** MinerU 方案解析一份含数学公式的 PDF
- **THEN** 输出内容中的公式 SHALL 以 LaTeX 形式呈现(行内公式与块级公式均予转换),不得丢失公式语义

#### Scenario: 表格转换为 HTML

- **WHEN** MinerU 方案解析一份含表格的 PDF
- **THEN** 输出内容中的表格 SHALL 转换为 HTML 表格结构,单元格行列关系 MUST 被保留

#### Scenario: 版面阅读顺序还原

- **WHEN** MinerU 方案解析一份多栏或图文混排的 PDF
- **THEN** 输出 SHALL 按讲义原文的阅读顺序组织段落与元素,避免双栏错读或图文错位

### Requirement: MinerU 执行模式与外部服务扩展位

MinerU 拆解 MUST 在 CPU pipeline 模式下本地执行(v1 不使用 GPU/vLLM 高精度引擎)。系统 SHALL 预留「外部 MinerU / GPU 服务」扩展位:当配置了外部 MinerU 服务 endpoint 时,SHALL 将拆解请求转发到该外部服务;未配置时 SHALL 退回本地 CPU pipeline。

#### Scenario: 未配置外部服务走本地 CPU pipeline

- **WHEN** 未配置任何外部 MinerU 服务 endpoint 且方案为 MinerU
- **THEN** 系统 SHALL 在本地以 CPU pipeline 模式执行 MinerU 拆解,不得依赖 GPU

#### Scenario: 配置外部 MinerU/GPU 服务时转发请求

- **WHEN** 用户在设置中配置了外部 MinerU / GPU 服务的 endpoint 且方案为 MinerU
- **THEN** 系统 SHALL 将 PDF 拆解请求转发到该外部服务,并接收其返回的结构化结果,本地不再执行重计算

### Requirement: PDF 拆解内容作为笔记生成的参考材料

PDF 拆解结果 MUST 作为参考材料喂给笔记生成阶段的 LLM。LLM SHALL 按讲义章节结构组织笔记,使生成的 Markdown 笔记与讲义结构对齐。参考材料 SHALL 以纯文本/Markdown 形式注入提示词(沿用基底 ai_srt2md 的 `generate_with_pdf_reference` 提示词分支),以节省 token。

#### Scenario: 笔记按讲义章节组织

- **WHEN** 笔记生成阶段在携带 PDF 拆解参考材料的情况下运行
- **THEN** LLM SHALL 按讲义检测到的章节结构组织输出笔记,使笔记的章节划分与讲义对齐

#### Scenario: 参考材料以纯文本注入以节省 token

- **WHEN** 系统将 PDF 拆解结果作为参考材料注入笔记生成提示词
- **THEN** 注入内容 SHALL 为纯文本/Markdown 形式,不得把 PDF 原始二进制或整页图像直接送入 LLM

#### Scenario: ASR 字幕与讲义参考共同驱动笔记

- **WHEN** 笔记生成阶段同时拥有 ASR 字幕文本与 PDF 讲义参考材料
- **THEN** 系统 SHALL 将字幕作为笔记内容主来源、讲义参考作为结构与术语校准来源一并注入 LLM,生成与视频内容一致且结构对齐讲义的笔记

### Requirement: PDF 解析失败的明确错误处理

PDF 解析过程中发生任何失败(如文件加密、文件损坏、pypdf 无法打开、MinerU 进程异常/超时)时,系统 MUST 产出明确、可定位的错误信息,SHALL 将错误归因到 PDF 解析这一步并暴露给任务状态,不得让流水线静默失败(silent fail)或以空内容继续生成笔记。

#### Scenario: 加密 PDF 报明确错误

- **WHEN** 系统尝试解析一份带打开密码的加密 PDF
- **THEN** 系统 SHALL 返回明确的「PDF 已加密、无法解析」错误,不得返回空文本冒充成功,且任务 SHALL 在 PDF 解析步骤标记为失败

#### Scenario: 损坏 PDF 报明确错误

- **WHEN** 系统尝试解析一份文件结构损坏、无法被打开的 PDF
- **THEN** 系统 SHALL 返回明确的「PDF 文件损坏、无法解析」错误并归因到 PDF 解析步骤,不得静默吞掉异常

#### Scenario: MinerU 拆解异常报明确错误

- **WHEN** MinerU 拆解进程崩溃、超时或返回非法结果
- **THEN** 系统 SHALL 捕获异常并返回明确的「MinerU 拆解失败」错误(含可定位原因),任务 SHALL 在 PDF 解析步骤标记为失败,不得用空内容继续后续笔记生成

