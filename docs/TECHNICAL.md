# 技术说明文档

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Vue3)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   首页       │  │   设置页     │  │      任务队列        │  │
│  │  - 文件上传  │  │  - API配置   │  │   - 实时状态         │  │
│  │  - 模型选择  │  │  - 系统设置  │  │   - 进度跟踪         │  │
│  │  - 进度显示  │  │              │  │   - 历史记录         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                      后端 (FastAPI)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   API 层     │  │   核心层     │  │      数据层          │  │
│  │  - 上传接口  │  │  - 处理管道  │  │   - SQLite           │  │
│  │  - 任务接口  │  │  - 语义对齐  │  │   - 文件存储         │  │
│  │  - 配置接口  │  │  - 内容过滤  │  │   - 任务队列         │  │
│  │  - 队列接口  │  │  - Markdown  │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   LLM 模块   │  │   解析器     │  │      后台工作器      │  │
│  │  - 多提供商  │  │  - SRT解析   │  │   - 异步处理         │  │
│  │  - 统一接口  │  │  - PDF解析   │  │   - 进度推送         │  │
│  │  - 提示词管  │  │  - TXT解析   │  │   - 错误处理         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 技术架构特点

1. **前后端分离**：前端 Vue3 + 后端 FastAPI，通过 RESTful API 通信
2. **异步处理**：使用后台工作器异步处理任务，避免阻塞主线程
3. **任务队列**：基于 SQLite 实现持久化任务队列，支持任务状态恢复
4. **多 LLM 支持**：工厂模式支持多种 LLM 提供商，统一接口调用
5. **模块化设计**：核心功能拆分为独立模块，便于维护和扩展

## 核心流程

### 1. 上传 -> 处理 -> 下载 完整流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  用户上传 │────▶│  文件验证 │────▶│  保存文件 │────▶│ 创建任务 │
│  文件     │     │  (类型/大小)    │  (本地存储)     │  (数据库) │
└──────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                                        │
┌──────────┐     ┌──────────┐     ┌──────────┐         │
│  下载结果 │◀────│  生成文件 │◀────│  LLM处理  │◀────────┘
│  (MD文件)│     │  (Markdown)   │  (内容重组)     │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              ┌──────────┐      ┌──────────┐      ┌──────────┐
              │ 解析字幕  │      │ 解析PDF   │      │ 语义对齐  │
              │ (SRT/TXT)│      │ (章节结构)│      │ (内容匹配)│
              └──────────┘      └──────────┘      └──────────┘
```

### 2. 详细处理流程

```
用户上传文件
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. 文件上传接口 (/api/v1/upload/task)   │
│    - 验证文件类型 (SRT/TXT/PDF)         │
│    - 验证文件大小 (< 50MB)              │
│    - 生成唯一文件 ID                    │
│    - 保存到本地存储                     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 2. 创建任务                             │
│    - 生成任务 ID (task_xxx)             │
│    - 保存文件路径到数据库               │
│    - 设置初始状态 (pending)             │
│    - 检查队列容量                       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 3. 开始处理 (/api/v1/process/start)     │
│    - 更新任务配置 (LLM提供商/模型)      │
│    - 启动后台工作器                     │
│    - 任务进入队列 (pending → processing)│
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 4. 后台处理管道 (Pipeline)              │
│                                          │
│  4.1 解析字幕 (10%)                     │
│      - SRT: 提取时间戳和文本            │
│      - TXT: 直接读取内容                │
│                                          │
│  4.2 解析PDF (30%)                      │
│      - 提取文本内容                     │
│      - 识别章节结构                     │
│      - 可选提取图片                     │
│                                          │
│  4.3 语义对齐 (50%)                     │
│      - 提取章节关键词                   │
│      - 匹配字幕与章节                   │
│      - 按章节分组内容                   │
│                                          │
│  4.4 内容过滤 (70%)                     │
│      - 规则过滤 (去除口语词)            │
│      - LLM分类 (chat/knowledge/transition)
│      - 精修内容                         │
│                                          │
│  4.5 生成Markdown (90%)                 │
│      - 批量调用LLM重组内容              │
│      - 生成目录结构                     │
│      - 格式化输出                       │
│                                          │
│  4.6 保存结果 (100%)                    │
│      - 写入输出目录                     │
│      - 更新任务状态 (completed)         │
│      - 生成下载链接                     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 5. 下载结果 (/api/v1/process/{id}/download)
│    - 验证任务完成状态                   │
│    - 读取生成的MD文件                   │
│    - 返回文件下载                       │
└─────────────────────────────────────────┘
```

### 3. 任务状态流转

```
                    ┌─────────────┐
         ┌─────────▶│   pending   │◀────────┐
         │          │  (待处理)   │         │
         │          └──────┬──────┘         │
         │                 │                │
         │  取消           ▼ 开始处理       │ 创建任务
         │          ┌─────────────┐         │
         └─────────│  processing │         │
                   │  (处理中)   │         │
                   └──────┬──────┘         │
                          │                │
           ┌──────────────┼──────────────┐ │
           ▼              ▼              ▼ │
    ┌─────────────┐ ┌─────────────┐ ┌──────────┐
    │  completed  │ │   failed    │ │cancelled │
    │  (已完成)   │ │  (失败)     │ │ (已取消) │
    └──────┬──────┘ └─────────────┘ └──────────┘
           │
           ▼
    可下载结果文件
```

## 数据模型

### 任务模型 (Task)

```python
@dataclass
class Task:
    """任务数据类"""
    # 基础信息
    id: str                          # 任务ID (task_xxxxxxxxxxxx)
    status: TaskStatus               # 状态枚举
    progress: int                    # 进度 (0-100)
    current_step: str                # 当前步骤描述
    message: Optional[str]           # 状态消息
    download_url: Optional[str]      # 下载链接

    # 文件路径
    srt_file: Optional[str]          # SRT文件路径
    txt_file: Optional[str]          # TXT文件路径
    pdf_file: Optional[str]          # PDF文件路径
    output_file: Optional[str]       # 输出文件路径

    # 原始文件名（用于下载时显示）
    srt_original_name: Optional[str]
    txt_original_name: Optional[str]
    pdf_original_name: Optional[str]

    # 元数据
    title: Optional[str]             # 文档标题
    created_at: datetime             # 创建时间
    updated_at: datetime             # 更新时间
    completed_at: Optional[datetime] # 完成时间

    # 处理配置
    extract_images: bool             # 是否提取图片
    llm_provider: Optional[str]      # LLM提供商
    llm_model: Optional[str]         # LLM模型

    # 错误信息
    error_message: Optional[str]
```

### 任务状态枚举

```python
class TaskStatus(str, Enum):
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
```

### 配置模型

```python
class AppConfig(BaseModel):
    """应用主配置"""
    version: str = "1.0"
    llm_provider: str = "qwen"  # 默认提供商

    # 各LLM提供商配置
    qwen: Optional[QwenConfig] = None
    glm: Optional[GLMConfig] = None
    deepseek: Optional[DeepSeekConfig] = None
    moonshot: Optional[MoonshotConfig] = None
    baidu: Optional[BaiduConfig] = None
    doubao: Optional[DoubaoConfig] = None
    minimax: Optional[MiniMaxConfig] = None

    # 处理选项
    processing: ProcessingConfig

    # 高级选项
    advanced: AdvancedConfig

    # 服务器配置
    server: ServerConfig
```

### 对齐段落模型

```python
@dataclass
class AlignedSegment:
    """对齐的段落"""
    chapter_title: str       # 章节标题
    chapter_level: int       # 章节层级
    start_time: str          # 开始时间
    end_time: str            # 结束时间
    content: str             # 内容文本
    keywords: List[str]      # 关键词列表
```

### 过滤结果模型

```python
@dataclass
class FilterResult:
    """过滤结果"""
    original_text: str       # 原始文本
    filtered_text: str       # 过滤后文本
    category: str            # 分类 (chat/knowledge/transition)
    confidence: float        # 置信度
    should_keep: bool        # 是否保留
```

## API 接口说明

### 文件上传接口

#### 上传 SRT 文件
```http
POST /api/v1/upload/srt
Content-Type: multipart/form-data

file: <SRT文件>
```

响应：
```json
{
  "file_id": "file_abc123def456",
  "filename": "course.srt",
  "file_type": "srt",
  "size": 10240,
  "message": "SRT文件上传成功"
}
```

#### 上传 TXT 文件
```http
POST /api/v1/upload/txt
Content-Type: multipart/form-data

file: <TXT文件>
```

#### 上传 PDF 文件
```http
POST /api/v1/upload/pdf
Content-Type: multipart/form-data

file: <PDF文件>
```

#### 创建任务
```http
POST /api/v1/upload/task?srt_file_id={srt_id}&pdf_file_id={pdf_id}&txt_file_id={txt_id}
```

响应：
```json
{
  "task_id": "task_abc123def456",
  "status": "pending",
  "message": "任务创建成功"
}
```

### 任务处理接口

#### 开始处理
```http
POST /api/v1/process/start
Content-Type: application/json

{
  "task_id": "task_abc123def456",
  "llm_provider": "qwen",
  "llm_model": "qwen-turbo",
  "extract_images": false,
  "image_quality": "medium"
}
```

#### 查询任务状态
```http
GET /api/v1/process/status/{task_id}
```

响应：
```json
{
  "task_id": "task_abc123def456",
  "status": "processing",
  "progress": 50,
  "current_step": "正在对齐内容...",
  "message": null,
  "download_url": null
}
```

#### 下载结果
```http
GET /api/v1/process/{task_id}/download
```

响应：文件下载 (Content-Type: text/markdown)

### 队列管理接口

#### 获取队列统计
```http
GET /api/v1/queue/stats
```

响应：
```json
{
  "pending_count": 2,
  "processing_count": 1,
  "completed_count": 10,
  "failed_count": 0,
  "total_count": 13,
  "max_queue_size": 20,
  "is_queue_full": false
}
```

#### 获取任务列表
```http
GET /api/v1/queue/tasks?status=processing&limit=20&offset=0
```

#### 取消任务
```http
POST /api/v1/queue/tasks/{task_id}/cancel
```

#### 删除任务
```http
DELETE /api/v1/queue/tasks/{task_id}
```

### 配置接口

#### 获取配置
```http
GET /api/v1/config
```

响应：
```json
{
  "version": "1.0",
  "llm_provider": "qwen",
  "qwen": {
    "api_key": "sk-***",
    "model": "qwen-turbo",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
  },
  "processing": {
    "extract_images": false,
    "image_quality": "medium",
    "output_format": "markdown",
    "language": "zh"
  },
  "advanced": {
    "chunk_size": 4000,
    "temperature": 0.3,
    "max_retries": 3
  }
}
```

#### 更新配置
```http
PUT /api/v1/config
Content-Type: application/json

{
  "llm_provider": "glm",
  "glm": {
    "api_key": "your-api-key",
    "model": "glm-4-flash"
  }
}
```

#### 验证 API Key
```http
POST /api/v1/config/verify
Content-Type: application/json

{
  "provider": "qwen",
  "api_key": "your-api-key"
}
```

### 日志接口

#### 获取后端日志
```http
GET /api/v1/logs/backend?level=INFO&task_id=xxx&lines=100
```

#### 获取前端日志
```http
GET /api/v1/logs/frontend?lines=100
```

## 配置说明

### 配置文件位置

- **开发环境**：`config/config.yaml`
- **Docker 环境**：通过环境变量配置

### 配置示例

```yaml
version: "1.0"
llm_provider: qwen  # 默认LLM提供商

# 通义千问配置
qwen:
  api_key: "sk-xxxxxxxxxxxxxxxx"
  model: "qwen-turbo"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 智谱AI配置
glm:
  api_key: "xxxxxxxxxxxxxxxx"
  model: "glm-4-flash"
  base_url: "https://open.bigmodel.cn/api/paas/v4/"

# DeepSeek配置
deepseek:
  api_key: "sk-xxxxxxxxxxxxxxxx"
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com/v1"

# Moonshot (Kimi)配置
moonshot:
  api_key: "sk-xxxxxxxxxxxxxxxx"
  model: "moonshot-v1-8k"
  base_url: "https://api.moonshot.cn/v1"

# 百度文心配置
baidu:
  api_key: "xxxxxxxxxxxxxxxx"
  secret_key: "xxxxxxxxxxxxxxxx"
  model: "ernie-bot-4"
  base_url: "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop"

# 字节豆包配置
doubao:
  api_key: "xxxxxxxxxxxxxxxx"
  model: "doubao-pro-4k"
  base_url: "https://ark.cn-beijing.volces.com/api/v3"

# MiniMax配置
minimax:
  api_key: "xxxxxxxxxxxxxxxx"
  group_id: "xxxxxxxxxxxxxxxx"
  model: "abab6.5-chat"
  base_url: "https://api.minimax.chat/v1"

# 处理选项
processing:
  extract_images: false       # 是否提取PDF图片
  image_quality: medium       # 图片质量 (low/medium/high)
  output_format: markdown     # 输出格式
  language: zh                # 语言 (zh/en)

# 高级选项
advanced:
  chunk_size: 4000            # 文本分块大小
  temperature: 0.3            # LLM温度参数
  max_retries: 3              # 最大重试次数

# 服务器配置
server:
  port: 8765                  # 服务端口
  host: "0.0.0.0"            # 绑定地址
  debug: false               # 调试模式
  temp_dir: "/tmp/course-doc-generator"  # 临时目录
```

### 环境变量配置 (Docker)

```bash
# LLM 配置
QWEN_API_KEY=your-qwen-api-key
QWEN_MODEL=qwen-turbo
GLM_API_KEY=your-glm-api-key
GLM_MODEL=glm-4-flash
DEFAULT_LLM_PROVIDER=qwen

# 处理选项
EXTRACT_IMAGES=false
IMAGE_QUALITY=medium
CHUNK_SIZE=4000
TEMPERATURE=0.3
MAX_RETRIES=3

# 服务器配置
PORT=5735
HOST=0.0.0.0
DEBUG=false
```

## 数据库设计

### 任务表 (tasks)

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    current_step TEXT,
    message TEXT,
    download_url TEXT,
    srt_file TEXT,
    txt_file TEXT,
    pdf_file TEXT,
    output_file TEXT,
    srt_original_name TEXT,
    txt_original_name TEXT,
    pdf_original_name TEXT,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    extract_images BOOLEAN DEFAULT 0,
    llm_provider TEXT,
    llm_model TEXT,
    error_message TEXT
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
```

## 性能优化

### 1. LLM 调用优化

- **批量处理**：每批处理 5 个 segments，减少 API 调用次数
- **快速模式**：短文件直接整体处理，不分段
- **Token 估算**：中文字符按 1.5 个 token 估算，避免超出限制
- **超时控制**：设置合理的超时时间，避免长时间等待

### 2. 文件处理优化

- **流式读取**：大文件使用流式读取，减少内存占用
- **异步保存**：文件保存使用异步操作
- **临时文件清理**：定期清理过期临时文件

### 3. 队列优化

- **队列容量限制**：最大 20 个并发任务，防止系统过载
- **优先级处理**：支持任务优先级设置
- **失败重试**：自动重试失败任务，最多 3 次

## 错误处理

### 错误码定义

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查请求参数 |
| 404 | 任务/文件不存在 | 确认任务ID正确 |
| 429 | 队列已满 | 等待后重试 |
| 500 | 服务器内部错误 | 查看日志排查 |

### 常见错误

1. **LLM API 调用失败**
   - 检查 API Key 是否有效
   - 检查网络连接
   - 检查模型名称是否正确

2. **PDF 解析失败**
   - 检查 PDF 是否加密
   - 检查 PDF 是否为扫描件
   - 尝试提取图片选项

3. **任务处理超时**
   - 增加超时时间设置
   - 减小分块大小
   - 使用更快的 LLM 模型

## 安全考虑

1. **文件上传安全**
   - 限制文件类型（仅 SRT/TXT/PDF）
   - 限制文件大小（最大 50MB）
   - 生成随机文件名，防止路径遍历攻击

2. **API Key 安全**
   - 存储在本地配置文件
   - 前端不直接访问 API Key
   - 支持 API Key 验证接口

3. **SQL 注入防护**
   - 使用参数化查询
   - 输入验证和过滤

## 扩展开发

### 添加新的 LLM 提供商

1. 在 `backend/src/llm/` 目录创建新的 LLM 类
2. 继承 `BaseLLM` 基类
3. 实现 `chat` 方法
4. 在 `LLMFactory` 中注册新提供商

示例：

```python
# backend/src/llm/new_provider.py
from .base import BaseLLM

class NewProviderLLM(BaseLLM):
    def chat(self, messages, **kwargs):
        # 实现对话逻辑
        pass

# backend/src/llm/factory.py
from .new_provider import NewProviderLLM

class LLMFactory:
    _providers = {
        # ... 其他提供商
        "new_provider": NewProviderLLM,
    }
```

### 添加新的文件解析器

1. 在 `backend/src/parsers/` 目录创建新的解析器
2. 实现解析接口
3. 在 `Pipeline` 中使用新解析器

### 自定义提示词

编辑 `backend/src/prompts/` 目录下的提示词文件：

- `classify.txt` - 内容分类提示词
- `restructure.txt` - 内容重组提示词
- `generate_directly.txt` - 直接生成提示词
- `generate_with_pdf_reference.txt` - 带PDF参考的生成提示词
- `pdf_structure_analysis.txt` - PDF结构分析提示词
