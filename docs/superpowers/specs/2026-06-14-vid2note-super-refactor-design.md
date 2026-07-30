# vid2note 超级重构设计稿

**日期**：2026-06-14
**作者**：brainstorming 流程产出
**状态**：设计已确认，待写实施计划

---

## 一、项目定位

把现有的 `ai_srt2md`（字幕上传 → Markdown 笔记）超级重构为 **`vid2note`**：输入视频链接，直接产出 Markdown 笔记 + 思维导图。

**核心定位**：
- **开源工具 + 个人本地**
- 客户端只做 **macOS arm64**（M4 Max Mac Studio 目标机）
- 同时支持 Docker 部署（CPU + GPU 双版）
- 同时保留 Web UI

**新仓库**：独立 repo（`vid2note`），原 `ai_srt2md` 作为参考。

---

## 二、关键决策（已锁定）

| 维度 | 决策 |
|------|------|
| 视频源 | YouTube + 国内平台（B站/抖音/西瓜/小红书）+ 直链 + 本地文件 |
| 下载工具 | yt-dlp + BBDown（B站首选）+ you-get（兜底） |
| 音频提取 | ffmpeg |
| ASR 在线 | bcut（默认、实验性、零配置） |
| ASR 本地 | FunASR + Qwen3-ASR（多档可选，按需下载） |
| LLM | 沿用现有 7 家 + 新增 Ollama |
| 客户端 | Electron + Vue3 + 完全内置 Python（PyInstaller） |
| Electron ↔ Python | 子进程 + HTTP |
| 任务模型 | 保留 SQLite 队列 + 后台 worker |
| 可恢复性 | 全链路 artifact-driven，每节点可独立重跑 |
| ASR 输出 | 默认 SRT，可选 TXT |
| 视频时长 | 不限 |
| 视频清理 | 默认删视频/音频，可配置保留 |
| 配置存储 | Electron：Keychain + Library；Docker：yaml + env |
| Python 打包 | PyInstaller |
| 测试覆盖率 | 80%+，三层（单元 + 集成 + E2E） |
| 实施节奏 | 中粒度计划 |
| 现有 LLM 链路 | 保留作为高级选项 |

---

## 三、仓库结构

```
vid2note/
├── README.md
├── LICENSE                            # MIT
├── pyproject.toml                     # uv/poetry workspace 根
├── Makefile                           # make dev / test / build / package
├── .env.example
├── .gitignore
│
├── core/                              # 纯 Python 业务库（无 FastAPI 依赖）
│   ├── pyproject.toml
│   ├── src/vid2note_core/
│   │   ├── __init__.py
│   │   ├── types.py                   # TaskId, ArtifactRef, NodeResult, ...
│   │   ├── errors.py                  # 统一异常体系 + 错误码
│   │   ├── downloaders/
│   │   │   ├── base.py                # IDownloader 接口
│   │   │   ├── ytdlp.py
│   │   │   ├── bbdown.py
│   │   │   ├── youget.py
│   │   │   ├── direct.py
│   │   │   ├── local_file.py
│   │   │   ├── router.py              # 自动路由 + fallback
│   │   │   └── binary_manager.py
│   │   ├── audio/
│   │   │   ├── extractor.py           # ffmpeg wrapper
│   │   │   └── ffmpeg_binary.py
│   │   ├── asr/
│   │   │   ├── base.py                # IASR 接口
│   │   │   ├── cloud/
│   │   │   │   └── bcut.py            # bcut 在线 ASR
│   │   │   ├── local/
│   │   │   │   ├── funasr.py
│   │   │   │   ├── qwen_asr.py
│   │   │   │   ├── model_manager.py
│   │   │   │   └── device.py
│   │   │   ├── output.py              # SRT/TXT 格式化
│   │   │   └── factory.py
│   │   ├── llm/                       # 7 家云端 + ollama + mock
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   ├── qwen.py / glm.py / deepseek.py / moonshot.py
│   │   │   ├── baidu.py / doubao.py / minimax.py / ollama.py / mock.py
│   │   ├── pipeline/
│   │   │   ├── node.py                # 抽象节点
│   │   │   ├── nodes/
│   │   │   │   ├── download.py
│   │   │   │   ├── extract_audio.py
│   │   │   │   ├── transcribe.py
│   │   │   │   ├── organize.py
│   │   │   │   ├── generate_mindmap.py
│   │   │   │   └── cleanup.py
│   │   │   ├── dag.py
│   │   │   └── context.py
│   │   ├── storage/
│   │   │   ├── db.py                  # SQLite
│   │   │   ├── task_repo.py
│   │   │   ├── artifact_store.py
│   │   │   └── migrations/
│   │   ├── prompts/                   # 沿用现有提示词
│   │   ├── config/
│   │   │   ├── models.py
│   │   │   ├── manager.py
│   │   │   └── keychain.py
│   │   └── utils/
│   │       ├── logger.py
│   │       ├── security.py
│   │       ├── rate_limiter.py
│   │       └── srt.py
│   └── tests/unit/                    # 单元测试
│
├── server/                            # FastAPI 包装层（薄）
│   ├── pyproject.toml
│   ├── src/vid2note_server/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── tasks.py               # POST 视频链路任务
│   │   │   ├── upload.py              # 上传本地文件（沿用）
│   │   │   ├── process.py             # 启动/查询/重跑
│   │   │   ├── download.py            # 下载产物
│   │   │   ├── config.py
│   │   │   ├── models.py              # ASR/LLM 模型管理
│   │   │   ├── events.py              # SSE
│   │   │   └── logs.py
│   │   ├── workers/task_worker.py
│   │   ├── schemas/
│   │   └── settings.py
│   └── tests/integration/
│
├── desktop/                           # Electron 客户端
│   ├── package.json
│   ├── electron-builder.yml           # mac arm64
│   ├── src/
│   │   ├── main/
│   │   │   ├── index.ts
│   │   │   ├── python_launcher.ts
│   │   │   ├── port_manager.ts
│   │   │   ├── model_downloader.ts
│   │   │   └── lifecycle.ts
│   │   ├── preload/index.ts
│   │   └── renderer/                  # Vue3，与 web/ 共享源码
│   │       ├── views/
│   │       ├── components/
│   │       ├── stores/
│   │       └── api/
│   ├── resources/                     # 内置二进制
│   │   ├── ffmpeg-mac-arm64
│   │   ├── yt-dlp-mac-arm64
│   │   ├── BBDown
│   │   ├── you-get
│   │   └── vid2note-server/           # PyInstaller 产物
│   └── tests/e2e/                     # Playwright
│
├── docker/
│   ├── Dockerfile.server.cpu
│   ├── Dockerfile.server.gpu
│   ├── docker-compose.cpu.yml
│   ├── docker-compose.gpu.yml
│   └── entrypoint.sh
│
├── web/                               # 纯 Web 前端（复用 renderer 源码）
│
├── scripts/
│   ├── build_desktop.sh
│   ├── build_docker.sh
│   └── fetch_binaries.sh
│
└── docs/
    ├── ARCHITECTURE.md
    ├── PIPELINE.md
    ├── CONTRIBUTING.md
    └── superpowers/specs/             # brainstorming 产物
```

**关键设计**：
- `core/` 是纯 Python 库，无 FastAPI 依赖，可被多种宿主（Electron、Docker、CLI、测试）共享
- `server/` 是 FastAPI 薄包装，只做 HTTP ↔ core 调用
- `desktop/renderer/` 和 `web/` 共享 Vue3 源码，构建目标不同
- ASR 本地模型不在仓库里，首次启动按需下载

---

## 四、Pipeline DAG 设计（核心）

### 节点抽象

```python
class PipelineNode(ABC):
    name: str                       # "download" / "transcribe" / ...
    requires: list[str]             # 上游 artifact key
    produces: list[str]             # 产出 artifact key

    @abstractmethod
    async def run(self, ctx: TaskContext) -> NodeResult: ...

    @abstractmethod
    async def resume(self, ctx: TaskContext) -> NodeResult: ...
    # artifact-driven：上游已落盘，run 和 resume 通常一样
```

### 拓扑

```
submit(url or file)
    ↓
download       ← ytdlp/bbdown/youget/direct/local_file
  produces: video.mp4
    ↓
extract_audio  ← ffmpeg
  produces: audio.wav (16kHz mono pcm_s16le)
    ↓
transcribe     ← bcut / funasr / qwen-asr
  produces: subtitle.srt (+ subtitle.txt 可选)
    ↓
organize       ← llm（7家 + ollama），可选 PDF 课件参考
  produces: notes.md
    ↓
generate_mindmap（可选）  ← 沿用现有逻辑
  produces: notes.xmind / notes.png
    ↓
cleanup        ← 默认删 video/audio，按配置保留
```

### Artifact 存储

```
data/tasks/<task_id>/
├── meta.json
├── status.json              # 各节点状态
├── artifacts/
│   ├── source.json          # 原始输入
│   ├── video.mp4
│   ├── audio.wav
│   ├── subtitle.srt
│   ├── subtitle.txt
│   ├── notes.md
│   ├── notes.xmind
│   ├── notes.png
│   └── optional_pdf.pdf     # 用户附带
└── logs/
    ├── pipeline.log
    └── <node>.log
```

### 重跑机制

```
POST /api/tasks/{id}/rerun                  # 从失败节点重跑（默认）
POST /api/tasks/{id}/rerun?from=transcribe  # 从指定节点重跑
POST /api/tasks/{id}/rerun?node=transcribe  # 只重跑单个节点
POST /api/tasks/{id}/rerun?from=download    # 完全重跑
```

**规则**：
- 节点开始前检查 `requires` artifact 是否存在
- 成功后写 `produces` artifact + 更新 `status.json`
- 重跑时，目标节点产物先删后跑
- `cleanup` 节点的"产物"是删除清单，记录在 status.json

### 任务状态机

```
pending → running → completed
                ↘ failed
                ↘ cancelled
                ↘ partial      ← 部分节点完成、部分失败（断点续传）
```

`partial` 状态可：
- 查看哪些节点已完成
- 从失败节点重跑
- 下载已完成的产物（如 SRT）

### 任务参数 vs 节点参数

- **任务参数**（创建时定，不可改）：URL、附加 PDF、ASR/LLM 提供商、是否生成思维导图
- **节点参数**（运行时定，可重跑时改）：ASR 模型档位、LLM 模型、temperature

重跑某节点时，可传入新参数（如换 ASR 提供商重跑 transcribe），不影响其他节点。

---

## 五、下载与音频模块

### 下载器抽象

```python
@dataclass
class DownloadResult:
    video_path: Path
    audio_path: Optional[Path]    # 有些下载器直接拉音频流
    metadata: dict                # title, duration, uploader
    raw_output: str

class IDownloader(ABC):
    name: str
    @abstractmethod
    def can_handle(self, url_or_path: str) -> bool: ...
    @abstractmethod
    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult: ...
```

### 路由策略

1. 本地文件路径 → LocalFileDownloader
2. 直链（.mp4/.m4a/.webm 等扩展名）→ DirectDownloader
3. youtube.com/youtu.be → YtDlpDownloader
4. bilibili.com → **BBDownDownloader**（B站最稳）
5. douyin/xigua/xhs → YtDlpDownloader（yt-dlp 部分支持）
6. 其他 → YtDlpDownloader（兜底，1000+ 站点）

**Fallback**：主下载器失败时尝试备选（BBDown 失败 → yt-dlp；yt-dlp 失败 → you-get）。

### 二进制管理

```python
class BinaryManager:
    def resolve(self) -> Path:
        """优先级：
        1. 环境变量 VID2NOTE_<NAME>_PATH
        2. 内置资源目录（Electron: desktop/resources/）
        3. 系统 PATH（Docker / 开发）
        4. 报错，提示用户安装
        """
```

`yt-dlp` 优先用 Python import 方式调用，失败回退二进制。

### FFmpeg 音频提取

- 默认 16kHz 单声道 wav（pcm_s16le）
- 自动检测容器
- 若下载器已拉音频流，跳过此节点

### Cookie 管理

- 客户端"Cookie 管理"页（按平台分组）
- 加密存 Keychain（macOS）/ yaml（Docker）
- 调用时通过参数传入，不写磁盘
- Cookie 失效 → 错误码 `COOKIE_EXPIRED`

### 错误分类（下载环节）

| 错误码 | 含义 | 重跑行为 |
|--------|------|---------|
| `DOWNLOAD_URL_INVALID` | URL 格式不对 | 不可重跑 |
| `DOWNLOAD_NETWORK_ERROR` | 网络超时/DNS | 可重跑（退避） |
| `DOWNLOAD_VIDEO_NOT_FOUND` | 视频被删/私密 | 不可重跑 |
| `DOWNLOAD_GEO_BLOCKED` | 地区限制 | 改代理后重跑 |
| `DOWNLOAD_COOKIE_EXPIRED` | Cookie 过期 | 更新后重跑 |
| `DOWNLOAD_RATE_LIMITED` | 被限流 | 等待后重跑 |
| `DOWNLOAD_BINARY_MISSING` | 二进制缺失 | 提示安装 |
| `DOWNLOAD_DISK_FULL` | 磁盘满 | 不可重跑 |

---

## 六、ASR 模块

### 接口

```python
@dataclass
class ASRSegment:
    start_ms: int
    end_ms: int
    text: str

@dataclass
class ASRResult:
    segments: list[ASRSegment]
    text_full: str
    language: str
    provider: str
    model_info: dict

class IASR(ABC):
    name: str
    is_cloud: bool
    requires_local_gpu: bool
    @abstractmethod
    def transcribe(self, audio_path: Path, opts: ASROpts) -> ASRResult: ...
    @abstractmethod
    def is_available(self) -> bool: ...
```

### 在线：bcut

```python
class BcutASR(IASR):
    """bcut 实验性在线 ASR 兼容方案（无需 Key）"""
    name = "bcut"
    is_cloud = True
    requires_local_gpu = False
```

**流程**：分块（60s）→ 上传 → 轮询 → 合并时间戳。

**风险**：外部服务或协议随时可能变化。
- 适配层隔离：所有调用细节集中在 `bcut.py` 一个文件
- 失败时明确错误码 `ASRTOOL_B_CHANGED`
- 后续可切换到官方 API

### 本地：FunASR / Qwen3-ASR

**FunASR 多档**：

| model_id | 体积 | 语言 | GPU 必需 | 描述 |
|----------|------|------|---------|------|
| `funasr-paraformer-small` | 350MB | zh | 否 | 中文快速版 |
| `funasr-sensevoice-small` | 600MB | zh/en/ja/ko/... | 否 | 多语言 |
| `funasr-paraformer-large` | 1.2GB | zh | 推荐 | 中文高精 |

**Qwen3-ASR**：

| model_id | 体积 | 语言 | GPU 必需 | 描述 |
|----------|------|------|---------|------|
| `qwen3-asr-base` | 1.8GB | zh/en | 是 | 通义 ASR |

### Model Manager

```python
class LocalModelManager:
    """
    存储位置：
    - macOS（Electron）：~/Library/Application Support/vid2note/models/
    - Linux（Docker）：/data/models/（compose 卷挂载）
    - 开发：./data/models/
    """
    def list_available(self) -> list[ModelInfo]: ...
    def list_installed(self) -> list[ModelInfo]: ...
    def download(self, model_id: str, progress_callback) -> None: ...
    def get_path(self, model_id: str) -> Path: ...
    def delete(self, model_id: str) -> None: ...
```

下载流程：modelscope / huggingface 拉 → sha256 校验 → 解压 → 写 manifest.json。

### 设备检测

```python
def detect_device() -> Literal["cuda", "mps", "cpu"]:
    if torch.cuda.is_available(): return "cuda"
    if torch.backends.mps.is_available(): return "mps"
    return "cpu"
```

影响 UI 可选项：
- CUDA → 全部模型可选
- MPS（Apple Silicon）→ 部分 FunASR 可选
- CPU → 只推荐轻量版，警告性能差

### 默认行为

**默认走实验性在线 bcut**（你的要求）。本地 ASR 作为可选。
- 首次启动检测设备，推荐对应档位
- 切换本地 ASR 时，如模型未下载，弹下载对话框

---

## 七、LLM 模块

### 沿用 7 家 + 新增 Ollama

```python
class OllamaLLM(BaseLLM):
    """本地 Ollama，OpenAI 兼容接口"""
    def __init__(self, api_key: str = "ollama",
                 model: str = "qwen2.5:7b",
                 base_url: str = "http://localhost:11434/v1", **kwargs): ...

    @staticmethod
    def check_service(base_url: str) -> dict:
        """返回 {running: bool, models: [...]}"""
```

**Ollama 集成**：
- 检测 11434 端口
- 列已 pull 的模型
- 模型未 pull 给指引（`ollama pull qwen2.5:7b`）
- 客户端 UI 有"打开 Ollama"按钮

### 整理流程

完全沿用现有 prompts 和 simple_processor 逻辑，迁移到 `core/pipeline/nodes/organize.py`。原 SRT 直传能力保留在"高级"区域。

---

## 八、配置系统

```python
class AppConfig(BaseModel):
    version: str
    run_mode: Literal["electron", "docker", "cli", "dev"]

    asr_provider: str = "bcut"
    llm_provider: str = "qwen"

    asr: ASRConfig
    qwen / glm / deepseek / moonshot / baidu / doubao / minimax / ollama
    processing: ProcessingConfig
    advanced: AdvancedConfig
    retention: RetentionConfig       # 视频/音频保留策略
    default_models: dict
    server: ServerConfig
```

**存储**：
- Electron：API Key → Keychain；非敏感 → `~/Library/Application Support/vid2note/config.yaml`
- Docker/CLI：全部 → `config/config.yaml` 或环境变量

```python
class ConfigManager:
    def __init__(self, run_mode: RunMode):
        self.secret_store = self._select_secret_store(run_mode)
        # Electron → KeychainSecretStore
        # Docker/CLI → YamlSecretStore

    def get_api_key(self, provider: str) -> str: ...
    def set_api_key(self, provider: str, key: str) -> None: ...
```

---

## 九、Docker 部署

### CPU 版

- 基础镜像：`python:3.11-slim`
- 内置：yt-dlp（pip）、you-get（pip）、BBDown（curl 二进制）、ffmpeg（apt）
- 体积：约 800MB
- 本地 ASR：CPU 模式（慢）

### GPU 版

- 基础镜像：`nvidia/cuda:12.1.0-runtime-ubuntu22.04`
- 同上 + CUDA + PyTorch GPU 版
- 体积：约 4GB
- 本地 ASR：CUDA 模式

### Compose 文件

CPU 与 GPU 各一份。GPU 版加 `deploy.resources.reservations.devices` 声明。

---

## 十、Electron 客户端

### 构建流程

```bash
# scripts/build_desktop.sh
1. cd core && pyinstaller ../desktop/vid2note-server.spec
   → 生成 vid2note-server 二进制
2. scripts/fetch_binaries.sh
   → 下载 ffmpeg-mac-arm64, yt-dlp-mac-arm64, BBDown, you-get
3. cd desktop && npm run build
   → Vue3 构建
4. electron-builder --mac --arm64
   → 生成 vid2note-x.x.x-arm64.dmg
```

### Electron 主进程

```typescript
async function launchPythonBackend(): Promise<number> {
  const port = await findFreePort();
  const serverPath = path.join(
    process.resourcesPath, 'vid2note-server', 'vid2note-server'
  );
  const child = spawn(serverPath, [], {
    env: {
      ...process.env,
      VID2NOTE_RUN_MODE: 'electron',
      VID2NOTE_PORT: String(port),
      VID2NOTE_DATA_DIR: userDataDir,
      VID2NOTE_RESOURCES_DIR: process.resourcesPath,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  await waitForHealth(`http://localhost:${port}/health`, 30000);
  return port;
}

app.on('quit', () => child.kill('SIGTERM'));
```

### 前端改造

1. **首页**：默认是"输入 URL"输入框；上传 SRT/TXT/PDF 退到"高级"区域
2. **任务详情页**：可视化 pipeline DAG，每节点显示状态/耗时/产物预览，失败节点带"重跑"按钮
3. **设置页增加**：
   - ASR 提供商选择（含本地模型管理：列出、下载、删除）
   - Ollama 配置（URL、检测、模型选择）
   - Cookie 管理（按平台）
   - 视频/音频保留策略
4. **模型下载弹窗**：带进度、可取消、断点续传

---

## 十一、测试 + 错误处理 + 模型管理

### 11.1 测试金字塔与覆盖率目标

```
                    ┌──────────┐
                    │   E2E    │   ~5%   ← Playwright，启动真实客户端跑 sample 视频
                    │  ~10 个  │
                  / └──────────┘ ┘
                /   ┌──────────┐
              /     │ Integ    │   ~15%  ← FastAPI + 真实 core，ASR/LLM/下载 mock
            /       │  ~50 个  │
          /         └──────────┘
        /           ┌──────────┐
      /             │  Unit    │   ~80%  ← 纯函数 + adapter，外部全 mock
    /               │ ~400 个  │
                    └──────────┘
```

**整体目标**：核心代码（`core/` + `server/`）行覆盖率 **≥ 80%**，关键模块（pipeline、storage、errors）**≥ 90%**。

**分层覆盖率目标**：

| 模块 | 覆盖率目标 | 说明 |
|------|----------|------|
| `core/types.py` | 100% | 数据类，纯函数 |
| `core/errors.py` | 100% | 错误类定义 |
| `core/utils/` | 95% | 工具函数 |
| `core/storage/` | 95% | DB + artifact，关键 |
| `core/config/` | 90% | 配置加载 |
| `core/downloaders/` | 85% | 适配器 + 路由 |
| `core/audio/` | 85% | ffmpeg wrapper |
| `core/asr/` | 85% | 适配器 + factory |
| `core/llm/` | 85% | 9 个 LLM 适配器 |
| `core/pipeline/` | 95% | DAG 编排，关键 |
| `server/api/` | 80% | 路由层 |
| `server/workers/` | 80% | worker |
| `desktop/` (TS) | 不强求 | E2E 覆盖关键路径 |

### 11.2 单元测试目录与用例清单

```
core/tests/unit/
├── conftest.py                    # 共享 fixtures
├── types/
│   └── test_types.py              # TaskId/ArtifactRef/NodeResult 序列化
├── errors/
│   └── test_errors.py             # 错误码、retryable、user_message
├── downloaders/
│   ├── test_router.py             # 路由选择 + fallback 链
│   ├── test_ytdlp.py
│   ├── test_bbdown.py
│   ├── test_youget.py
│   ├── test_direct.py
│   ├── test_local_file.py
│   └── test_binary_manager.py     # resolve() 优先级
├── audio/
│   └── test_extractor.py          # ffmpeg 命令拼装、错误处理
├── asr/
│   ├── test_bcut.py               # bcut 分块/合并/轮询
│   ├── test_funasr.py
│   ├── test_qwen_asr.py
│   ├── test_output.py             # SRT/TXT 格式化（纯函数）
│   ├── test_device.py             # detect_device（mock torch）
│   ├── test_model_manager.py      # 下载/校验/删除
│   └── test_factory.py
├── llm/
│   ├── test_qwen.py / test_glm.py / test_deepseek.py
│   ├── test_moonshot.py / test_baidu.py / test_doubao.py
│   ├── test_minimax.py / test_ollama.py / test_mock.py
│   ├── test_factory.py
│   └── test_glm_reasoning.py      # glm-4.7 reasoning_content 提取（沿用现有特殊逻辑）
├── pipeline/
│   ├── test_node.py               # 抽象节点接口
│   ├── test_dag.py                # 拓扑校验、循环检测、重跑
│   ├── test_context.py            # TaskContext
│   ├── test_nodes_download.py
│   ├── test_nodes_extract_audio.py
│   ├── test_nodes_transcribe.py
│   ├── test_nodes_organize.py
│   ├── test_nodes_generate_mindmap.py
│   └── test_nodes_cleanup.py
├── storage/
│   ├── test_db.py                 # 连接管理、迁移、单例
│   ├── test_task_repo.py          # CRUD、状态转换、reserve_pending_task
│   ├── test_artifact_store.py     # 文件读写、路径校验
│   └── test_migrations.py
├── config/
│   ├── test_manager.py            # 加载、保存、env 覆盖、热重载
│   ├── test_models.py             # Pydantic 校验
│   └── test_keychain.py           # macOS Keychain 适配（mock `security` 命令）
└── utils/
    ├── test_logger.py
    ├── test_security.py           # is_safe_path、secure_filename、prompt 注入防护
    ├── test_rate_limiter.py
    └── test_srt.py                # SRT 解析、合并、分段
```

**重点用例**（必须有）：

- **download/test_router.py**：
  - youtube.com → ytdlp
  - bilibili.com → bbdown（首选）
  - bilibili.com + bbdown 失败 → fallback 到 ytdlp
  - bilibili.com + bbdown+ytdlp 都失败 → fallback 到 youget
  - 本地路径 → local_file
  - .mp4 直链 → direct
  - 未知站点 → ytdlp 兜底
- **pipeline/test_dag.py**：
  - 上游 artifact 不存在 → 报错
  - 重跑 download → 删全部下游 artifact
  - 重跑 transcribe → 只删 srt/txt/md/xmind
  - 重跑 organize → 只删 md/xmind
  - cleanup 节点失败不影响主链路完成状态
  - `partial` 状态可单独下载已完成产物
- **storage/test_task_repo.py**：
  - `reserve_pending_task` 原子性（多线程并发只 reserve 一次）
  - 状态机非法转换拒绝（completed → pending）
  - 数据库迁移幂等
- **asr/test_bcut.py**：
  - 超长音频自动分块（>60s）
  - 分块时间戳拼接正确
  - b 接口返回错误结构 → 错误码 `ASRTOOL_B_CHANGED`
  - 网络超时 → 重试 + 最终失败
- **utils/test_security.py**：
  - 路径遍历攻击（`../../etc/passwd`）拦截
  - file_id 格式校验
  - 提示词注入（`</system>`、`ignore previous`）检测
- **config/test_keychain.py**：
  - 写入 → 读取 → 删除 roundtrip（mock `security` CLI）
  - Keychain 不可用 fallback 到 yaml

### 11.3 集成测试

```
server/tests/integration/
├── conftest.py                    # 起 TestClient、mock 外部依赖
├── test_api_tasks.py              # POST /tasks（URL 输入）全流程
├── test_api_upload.py             # 上传本地文件
├── test_api_process.py            # 启动/查询/重跑
├── test_api_download.py           # 下载 md/srt/xmind
├── test_api_config.py             # 配置 CRUD
├── test_api_models.py             # ASR 模型列表/下载/删除
├── test_api_events.py             # SSE 推送
├── test_full_pipeline_url.py      # URL → md，mock 各节点
├── test_full_pipeline_local.py    # 本地文件 → md
├── test_resume_pipeline.py        # 失败后从指定节点重跑
├── test_partial_state.py          # partial 状态下载产物
├── test_worker_concurrency.py     # 3 并发 + 队列满拒绝
├── test_cleanup_behavior.py       # 默认删视频/音频 + 保留策略
└── test_error_codes.py            # 各种错误码 → HTTP 响应
```

**测试方式**：FastAPI `TestClient` + 真实 `core/` + mock 所有外部（subprocess、httpx、OpenAI、模型加载）。SQLite 用临时文件。

**重点用例**：

- **test_full_pipeline_url.py**：
  - POST URL → 任务 pending
  - 触发 worker → download（mock 返回 fixture mp4）→ audio → transcribe（mock 返回 fixture srt）→ organize（mock LLM 返回 md）→ mindmap → cleanup → completed
  - 全程 SSE 推送 6 个 node.completed 事件
  - 最终 GET /download 返回 md 内容
- **test_resume_pipeline.py**：
  - 跑到 transcribe 失败（mock asr 抛错）
  - 任务变 partial
  - POST /rerun → 从 transcribe 重跑（mock 这次成功）
  - 任务 completed
  - 验证 download 步骤**没有**重新执行（download artifact 未变）
- **test_worker_concurrency.py**：
  - 提交 5 个任务，max_concurrent=3
  - 前 3 个进入 processing，后 2 个 pending
  - 前 3 个完成，后 2 个自动进入 processing

### 11.4 E2E 测试（Playwright）

```
desktop/tests/e2e/
├── fixtures/
│   ├── sample-video.mp4           # 30 秒英文 + 中文混合
│   ├── sample-video.srt           # 对应正确 SRT（Golden）
│   └── sample-url.txt             # 一个稳定的公开视频 URL（或本地 file://）
├── test_electron_startup.spec.ts  # 启动、Python 后端健康检查
├── test_url_input.spec.ts         # 输入 URL → 等完成 → 下载 md
├── test_local_file.spec.ts        # 拖拽本地视频 → 出笔记
├── test_pipeline_ui.spec.ts       # DAG 可视化显示状态
├── test_rerun.spec.ts             # 失败节点重跑
├── test_settings_asr.spec.ts      # 切换 ASR 提供商
├── test_settings_llm.spec.ts      # 配置 LLM API Key
├── test_settings_ollama.spec.ts   # 检测 Ollama 服务
├── test_model_download.spec.ts    # 模型下载弹窗、进度、取消
└── test_cookie_manage.spec.ts     # Cookie 管理 UI
```

**E2E 策略**：
- **不依赖外部网络**：默认用 `file://` 加载本地 sample 视频，或 mock yt-dlp
- **Golden 对比**：sample 视频的 SRT 是固定的，每次 E2E 跑出的 ASR 结果与 Golden 做相似度对比（>80% 即通过）
- **CI 中标记 `@slow`**：本地 ASR 完整跑一遍很慢，CI 默认跑 cloud ASR（mock），`@slow` 仅 nightly 跑

### 11.5 Golden Dataset（精度评估）

`tests/golden/`：

```
golden/
├── dataset-1/
│   ├── input.mp4                  # 30s，中文讲解
│   ├── expected.srt               # 人工校对的金标 SRT
│   ├── expected.md                # 人工整理的金标笔记
│   └── meta.json                  # asr_provider, llm_provider
├── dataset-2/
│   ├── input.mp4                  # 60s，英文 + 中文混合
│   ├── expected.srt
│   └── ...
├── dataset-3/
│   └── ...                        # 长视频（10 分钟+）
└── README.md                      # 如何添加新 dataset
```

**评估脚本** `scripts/eval_golden.py`：

- 跑每个 dataset 通过完整 pipeline
- ASR 输出与 expected.srt 计算 WER（词错误率，用 jiwer 库）
- LLM 输出与 expected.md 计算 ROUGE-L
- 生成报告 `golden_report.html`：每个 dataset 的 WER/ROUGE、对比表
- **不阻塞 CI**（手动跑或 nightly 跑），但阈值不达标会在 PR 评论里提示

**阈值**：
- ASR WER < 15%（中文）/ 20%（英文）
- LLM ROUGE-L > 0.4

### 11.6 Mock 策略详解

| 外部依赖 | Mock 方式 | 工具 |
|---------|----------|------|
| yt-dlp（Python import） | monkeypatch `yt_dlp.YoutubeDL.download` | pytest monkeypatch |
| BBDown / you-get / ffmpeg | mock `subprocess.run`，返回 fixture 文件 | pytest monkeypatch |
| ASR 在线（bcut） | mock `httpx.AsyncClient`，按场景返回 | respx |
| ASR 本地（FunASR/Qwen3-ASR） | mock 模型类 `AutoModel.from_pretrained` | pytest monkeypatch |
| LLM 云端 | mock `openai.OpenAI` client | unittest.mock |
| Ollama | mock `httpx` | respx |
| SQLite | 临时文件 `tmp_path_factory` | pytest 内置 |
| macOS Keychain | mock `subprocess.run(['security', ...])` | pytest monkeypatch |
| 文件系统 | 临时目录 `tmp_path` | pytest 内置 |
| 时间 | `freezegun.freeze_time` | freezegun |

**conftest.py 共享 fixtures**：

```python
# core/tests/unit/conftest.py 关键 fixtures
@pytest.fixture
def tmp_task_dir(tmp_path_factory) -> Path:
    """临时任务目录，含 artifacts/ logs/ 子目录"""

@pytest.fixture
def mock_ytdlp(monkeypatch, fixtures_dir):
    """mock yt-dlp，把指定 fixture mp4 复制到目标位置"""

@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """mock ffmpeg 抽音频，复制 fixture wav"""

@pytest.fixture
def mock_asr_cloud(monkeypatch):
    """mock bcut 在线 ASR，返回 fixture ASRResult"""

@pytest.fixture
def mock_llm(monkeypatch):
    """mock LLM 返回 fixture markdown"""

@pytest.fixture
def sample_task_context(tmp_task_dir) -> TaskContext:
    """预填充的 TaskContext"""
```

### 11.7 CI/CD 流水线

**GitHub Actions**（`.github/workflows/`）：

```
workflows/
├── ci-core.yml                # core 单元测试（push/PR 触发）
├── ci-server.yml              # server 集成测试
├── ci-desktop.yml             # 桌面端 Lint + 单元测试
├── ci-coverage.yml            # 覆盖率上报（Codecov）
├── ci-lint.yml                # ruff (py) + eslint (ts) + prettier
├── ci-typecheck.yml           # mypy (py) + tsc (ts)
├── e2e-mac.yml                # E2E（macOS runner，仅 main 分支 + 手动）
├── build-docker-cpu.yml       # 构建 CPU 镜像
├── build-docker-gpu.yml       # 构建 GPU 镜像
├── build-mac-arm64.yml        # 构建 dmg（macOS runner）
├── nightly-golden.yml         # nightly 跑 Golden dataset
└── release.yml                # tag 触发，发布到 GitHub Releases
```

**ci-core.yml 关键步骤**：

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ matrix.python }} }
      - run: pip install uv && uv sync --all-extras
      - run: uv run pytest core/tests/unit/ --cov=vid2note_core --cov-report=xml --cov-report=term -v
      - uses: codecov/codecov-action@v4
        with: { files: ./coverage.xml }
      - name: 覆盖率门禁
        run: |
          COV=$(uv run pytest --cov=vid2note_core --cov-report=term-missing -q | grep TOTAL | awk '{print $NF}' | tr -d '%')
          if [ $COV -lt 80 ]; then echo "覆盖率 $COV% 低于 80%"; exit 1; fi
```

**预合并门禁**：
- ✅ 单元测试全过
- ✅ 集成测试全过
- ✅ Lint（ruff/eslint）无错
- ✅ Type check（mypy/tsc）无错
- ✅ 核心模块覆盖率 ≥ 80%
- ✅ 关键模块覆盖率 ≥ 90%
- ⚠️ E2E 通过（仅 macOS runner，main 分支）

### 11.8 本地开发测试流程

**Makefile** 提供统一入口：

```makefile
.PHONY: dev test test-unit test-integ test-e2e coverage lint typecheck golden package

dev:                ## 启动开发服务（hot reload）
	uv run uvicorn vid2note_server.main:app --reload

test:               ## 跑所有测试
	uv run pytest core/tests/ server/tests/

test-unit:          ## 只跑单元测试
	uv run pytest core/tests/unit/ -v

test-integ:         ## 只跑集成测试
	uv run pytest server/tests/integration/ -v

test-e2e:           ## E2E（需要先构建客户端）
	cd desktop && npx playwright test

test-watch:         ## 监听模式
	uv run pytest-watch core/tests/

coverage:           ## 生成覆盖率报告
	uv run pytest --cov=vid2note_core --cov=vid2note_server --cov-report=html
	open htmlcov/index.html

lint:               ## Lint
	uv run ruff check . && cd desktop && npm run lint

typecheck:          ## 类型检查
	uv run mypy core/src/ server/src/ && cd desktop && npm run typecheck

golden:             ## 跑 Golden 评估
	uv run python scripts/eval_golden.py

test-fast:          ## 跳过 slow 标记的快速测试
	uv run pytest -m "not slow"
```

**测试标记**（pytest markers）：

- `@pytest.mark.slow`：耗时长（>5s），CI 默认跳过
- `@pytest.mark.network`：需要网络，CI 默认跳过
- `@pytest.mark.golden`：Golden dataset 相关
- `@pytest.mark.gpu`：需要 GPU

`pytest.ini`：

```ini
[pytest]
markers =
    slow: 耗时长的测试
    network: 需要网络
    golden: Golden dataset
    gpu: 需要 GPU
addopts = -ra --strict-markers --cov-fail-under=80
testpaths = core/tests server/tests
```

### 11.9 测试数据与 fixtures

`tests/fixtures/`：

```
fixtures/
├── videos/
│   ├── 30s-zh.mp4               # 30 秒中文
│   ├── 30s-en.mp4               # 30 秒英文
│   ├── 5min-mixed.mp4           # 5 分钟中英混合
│   └── corrupt.mp4              # 损坏文件（测错误处理）
├── audio/
│   ├── 30s-zh.wav               # 对应 wav
│   └── 30s-en.wav
├── srt/
│   ├── 30s-zh.srt               # 对应金标 SRT
│   └── 30s-en.srt
├── llm-responses/
│   ├── 30s-zh-notes.md          # LLM 整理输出
│   └── ...
├── pdf/
│   └── sample-course.pdf        # PDF 课件 sample
└── mocks/
    ├── bcut-response-30s.json
    ├── ytdlp-output-youtube.txt
    └── bbdown-output-bilibili.txt
```

**fixtures 来源**：
- 用户自己录制（或公开课切片）→ 已授权可公开
- 用 ffmpeg 合成（TTS 生成音频 → 合成视频）
- 加入仓库前用 `git lfs` 处理大文件

### 11.10 错误体系

```python
class Vid2NoteError(Exception):
    code: str
    retryable: bool
    user_message: str

class DownloadError(Vid2NoteError): ...
class ASRError(Vid2NoteError): ...
class LLMError(Vid2NoteError): ...
class PipelineError(Vid2NoteError): ...
```

每类一组具体错误码（如 `DOWNLOAD_COOKIE_EXPIRED`、`ASRTOOL_B_CHANGED`）。

**API 统一错误响应**：

```json
{
  "error": {
    "code": "DOWNLOAD_COOKIE_EXPIRED",
    "message": "Cookie 已过期，请到设置页更新",
    "retryable": false,
    "step": "download",
    "task_id": "task_xxx"
  }
}
```

### 错误体系

```python
class Vid2NoteError(Exception):
    code: str
    retryable: bool
    user_message: str

class DownloadError(Vid2NoteError): ...
class ASRError(Vid2NoteError): ...
class LLMError(Vid2NoteError): ...
class PipelineError(Vid2NoteError): ...
```

每类一组具体错误码（如 `DOWNLOAD_COOKIE_EXPIRED`、`ASRTOOL_B_CHANGED`）。

**API 统一错误响应**：

```json
{
  "error": {
    "code": "DOWNLOAD_COOKIE_EXPIRED",
    "message": "Cookie 已过期，请到设置页更新",
    "retryable": false,
    "step": "download",
    "task_id": "task_xxx"
  }
}
```

### 日志

- 任务级：`logs/pipeline.log`
- 节点级：`logs/<node>.log`
- 结构化 JSON 日志，前端可解析展示

### 进度推送（SSE）

```
GET /api/tasks/{id}/events    # SSE
```

事件：
- `task.started`
- `node.started {node: "download"}`
- `node.progress {node: "download", progress: 50, message: "..."}`
- `node.completed {node: "download", artifacts: [...]}`
- `node.failed {node: "download", error: {...}}`
- `task.completed`
- `task.failed`

前端 EventSource 订阅。轮询保留作 fallback。

### 模型管理 API

```
GET    /api/models/asr/available          # 所有支持的 ASR 模型
GET    /api/models/asr/installed          # 已下载的本地模型
POST   /api/models/asr/download           # 下载（支持取消）
DELETE /api/models/asr/{model_id}         # 删除
GET    /api/models/asr/download/progress  # SSE 进度

GET    /api/models/llm/available          # 各 LLM 提供商的可用模型
GET    /api/models/llm/ollama/status      # Ollama 状态
GET    /api/models/llm/ollama/models      # Ollama 已 pull 模型
```

---

## 十二、实施路线图

```
Phase 0:  仓库初始化 + 文档骨架                            [0.5d]
Phase 1:  core/ 基础设施（types/errors/logger/storage）    [1d]
Phase 2:  迁移现有 LLM 模块到 core/llm/                    [1d]
Phase 3:  迁移 SRT/PDF 解析 + prompts 到 core/             [0.5d]
Phase 4:  实现 downloaders（含 router、fallback）          [2d]
Phase 5:  实现 audio/extractor                             [0.5d]
Phase 6:  实现在线 ASR（bcut）                             [1.5d]
Phase 7:  实现 ASR local（FunASR + Qwen3-ASR + Manager）   [3d]
Phase 8:  实现 pipeline DAG（node/dag/context + 6 节点）   [2d]
Phase 9:  实现 server/ FastAPI 薄包装（api/workers/sse）   [2d]
Phase 10: 集成测试 + Golden Dataset                         [1d]
Phase 11: 配置系统重构（yaml + keychain + env）             [1d]
Phase 12: Vue3 前端改造（URL 输入、DAG 可视化、模型管理）   [3d]
Phase 13: Docker（CPU + GPU 双镜像 + compose）              [1d]
Phase 14: Electron 客户端（python_launcher、IPC、preload）  [2d]
Phase 15: PyInstaller 打包脚本 + 二进制内置                 [1d]
Phase 16: electron-builder mac arm64 dmg                    [0.5d]
Phase 17: Ollama 接入                                       [0.5d]
Phase 18: E2E (Playwright) + 文档 + README                  [1d]
─────────────────────────────────────────────────
总计约 25 个工作日（writing-plans 阶段细化）
```

**关键里程碑**：
- Phase 1-11 完成 → Docker 跑通视频链路（含完整配置系统）
- Phase 12-16 完成 → 客户端可用
- Phase 17-18 完成 → 全功能上线

---

## 十三、未列入一期范围（YAGNI）

- 多用户系统 / 权限 / 计费（个人本地工具不需要）
- 移动端 App
- Windows / Linux 客户端（只做 macOS arm64）
- 微服务拆分（运行一体）
- WebSocket 双向通信（SSE 单向已够）
- 视频剪辑 / 编辑功能（只做转笔记）

---

## 十四、风险与对策

| 风险 | 对策 |
|------|------|
| bcut 外部服务或协议随时变化 | 适配层隔离；明确错误码；本地 ASR 兜底 |
| PyInstaller + PyTorch 打包冲突 | 提前在 Phase 15 做最小打包验证；备选 pyoxidizer |
| Electron 体积过大（>1GB） | 模型不入包，按需下载；ffmpeg/yt-dlp 等用预编译压缩版 |
| FunASR 在 Apple Silicon 不稳 | MPS 兼容性提前测；fallback CPU |
| Ollama 服务未启动 | 客户端 UI 引导安装；明确错误提示 |
| 国内平台 Cookie 频繁失效 | Cookie 失效明确错误码；客户端 UI 一键更新 |
| 超长视频 LLM 上下文超限 | organize 节点内部分块 + 合并；监控 token 用量 |

---

## 十五、下一步

1. **用户审阅本文档**
2. 进入 writing-plans 流程，把 Phase 0-18 拆成可执行的子任务（中粒度，每个子任务有验收标准）
3. 实施计划保存到 `docs/superpowers/plans/2026-06-14-vid2note-implementation.md`
