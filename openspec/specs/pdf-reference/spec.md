# pdf-reference Specification

## Purpose

定义可选 PDF 讲义的校验、基础文本提取和笔记参考行为。复杂 OCR/MinerU 解析不属于当前稳定能力。

## Requirements

### Requirement: PDF 讲义作为可选输入

系统 MUST 允许任务附带至多一份 PDF。未附带 PDF 时流水线 MUST 正常运行。

#### Scenario: 不附带讲义

- **WHEN** 用户只提交视频或音频
- **THEN** 系统 SHALL 在无 PDF 参考的情况下生成笔记

#### Scenario: 附带一份讲义

- **WHEN** 用户创建任务时上传一份有效 PDF
- **THEN** 系统 SHALL 保存文件、绑定到任务并在笔记节点解析

### Requirement: 上传校验

PDF 上传 MUST 使用流式写入，MUST 校验扩展名、MIME、PDF 文件头和配置的大小上限。失败时不得留下半成品。

#### Scenario: 伪造 PDF

- **WHEN** 文件名为 `.pdf` 但内容没有有效 PDF 文件头
- **THEN** API SHALL 返回 400 且不得创建任务

#### Scenario: 文件超过上限

- **WHEN** PDF 超过 `MAX_PDF_UPLOAD_MB`
- **THEN** API SHALL 中止写入、删除部分文件并返回明确错误

### Requirement: 基础文本与章节提取

系统 MUST 使用 PyMuPDF 提取文字层，并 SHALL 识别常见章节标题及页码。扫描件不承诺 OCR。

#### Scenario: 带文字层的讲义

- **WHEN** PDF 包含可提取文字和章节标题
- **THEN** 解析结果 SHALL 包含全文、分页文本与检测到的章节

#### Scenario: 扫描件

- **WHEN** PDF 只有图像而没有文字层
- **THEN** 系统 SHALL 不得编造文本；生成效果可降级，界面和文档 SHALL 说明当前不含 OCR

### Requirement: 讲义辅助笔记生成

字幕 MUST 是笔记内容的主来源；PDF 文本 SHALL 作为结构和术语参考，以文本形式注入 LLM，不得发送 PDF 原始二进制。

#### Scenario: 同时存在字幕和讲义

- **WHEN** 笔记节点同时拥有 SRT 和 PDF
- **THEN** 系统 SHALL 走带讲义参考的 Prompt 分支，并保持内容与视频字幕一致

### Requirement: 错误可定位

加密、损坏或无法解析的 PDF MUST 使笔记节点失败并记录可定位原因，不得静默使用空结果冒充成功。

#### Scenario: 损坏文件

- **WHEN** PyMuPDF 无法打开已上传文件
- **THEN** 任务 SHALL 在笔记节点失败并保留错误信息供本地用户排查
