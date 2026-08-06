## MODIFIED Requirements

### Requirement: 基础文本与章节提取

系统 MUST 使用 `pypdf` 提取文字层，并 SHALL 识别常见章节标题及页码。基础模式 MUST NOT 依赖 PyMuPDF/`fitz`，扫描件不承诺 OCR。

#### Scenario: 带文字层的讲义

- **WHEN** PDF 包含可提取文字和章节标题
- **THEN** 解析结果 SHALL 包含全文、分页文本与检测到的章节

#### Scenario: 扫描件

- **WHEN** PDF 只有图像而没有文字层
- **THEN** 系统 SHALL 不得编造文本；生成效果可降级，界面和文档 SHALL 说明当前不含 OCR

#### Scenario: 运行依赖审计

- **WHEN** 检查生产依赖和 PDF 解析源码
- **THEN** 依赖清单和稳定解析路径 MUST NOT 包含 PyMuPDF 或 `fitz`

### Requirement: 错误可定位

加密、损坏或无法解析的 PDF MUST 使笔记节点失败并记录可定位原因，不得静默使用空结果冒充成功。

#### Scenario: 损坏文件

- **WHEN** `pypdf` 无法打开已上传文件
- **THEN** 任务 SHALL 在笔记节点失败并保留错误信息供本地用户排查
