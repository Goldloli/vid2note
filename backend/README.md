# 课程字幕整理工具 - 后端服务

## 项目结构

```
backend/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI 主应用入口
│   ├── api/                 # API 路由
│   │   ├── __init__.py
│   │   ├── upload.py        # 文件上传接口
│   │   ├── process.py       # 任务处理接口
│   │   └── config.py        # 配置管理接口
│   ├── config/              # 配置管理模块
│   │   ├── __init__.py
│   │   ├── models.py        # Pydantic 配置模型
│   │   └── manager.py       # 配置管理器
│   ├── parsers/             # 输入解析模块
│   │   ├── __init__.py
│   │   ├── srt_parser.py    # SRT 字幕解析器
│   │   └── pdf_parser.py    # PDF 课件解析器
│   ├── llm/                 # LLM 接口模块
│   │   ├── __init__.py
│   │   ├── base.py          # LLM 抽象基类
│   │   ├── qwen.py          # 通义千问实现
│   │   ├── glm.py           # 智谱AI实现
│   │   └── factory.py       # LLM 工厂类
│   ├── core/                # 核心处理模块
│   │   ├── __init__.py
│   │   ├── aligner.py       # 语义对齐
│   │   ├── filter.py        # 内容过滤
│   │   └── generator.py     # Markdown生成器
│   ├── tasks/               # 任务队列模块
│   │   ├── __init__.py
│   │   └── pipeline.py      # 处理管道
│   ├── utils/               # 工具函数
│   │   └── __init__.py
│   └── prompts/             # Prompt 文件
│       ├── classify.txt
│       └── restructure.txt
├── requirements.txt
├── run.py
└── README.md
```

## 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

## 启动服务

```bash
python run.py
```

服务将在 http://0.0.0.0:5735 启动

## API 接口

### 文件上传
- `POST /api/v1/upload/srt` - 上传 SRT 字幕文件
- `POST /api/v1/upload/pdf` - 上传 PDF 课件文件
- `POST /api/v1/upload/task` - 创建处理任务

### 任务处理
- `POST /api/v1/process/start` - 开始处理任务
- `GET /api/v1/process/status/{task_id}` - 查询任务状态
- `GET /api/v1/process/{task_id}/download` - 下载处理结果

### 配置管理
- `GET /api/v1/config` - 获取当前配置
- `PUT /api/v1/config` - 更新配置
- `POST /api/v1/config/verify` - 验证 API Key
- `GET /api/v1/config/models` - 获取可用模型列表

## 环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
# LLM 配置
QWEN_API_KEY=your_qwen_api_key
GLM_API_KEY=your_glm_api_key
DEFAULT_LLM_PROVIDER=qwen

# 服务配置
PORT=5735
HOST=0.0.0.0
DEBUG=false
```
