# vid2note 架构文档

## Monorepo 结构

```
vid2note/
├── core/      # 纯 Python 业务库（无 FastAPI 依赖，可被多宿主复用）
├── server/    # FastAPI 薄包装层（HTTP ↔ core）
├── desktop/   # Electron + Vue3 客户端
├── scripts/   # 构建/打包/评估脚本
├── docs/      # 文档
└── docker/    # Docker 配置
```

## 三层职责分离

| 层 | 职责 | 关键约束 |
|----|------|----------|
| `core/` | 业务核心：Pipeline DAG、ASR、LLM、下载器、存储 | 不依赖 FastAPI / Electron |
| `server/` | HTTP 路由：tasks/process/upload/config/events | 只做 HTTP ↔ core 调用 |
| `desktop/` | UI：主控台/详情/设置 + Electron 主进程 | 通过 HTTP/SSE 与 server 通信 |

## 核心数据流

```
用户输入 URL
  → server POST /tasks（创建 pending 任务）
  → TaskWorker 轮询 → reserve_pending_task 原子抢占
  → PipelineDAG.run() 顺序执行 6 节点：
      Download → ExtractAudio → Transcribe → Organize → Mindmap → Cleanup
  → 每节点产出 artifact 落盘到 ArtifactStore
  → EventBus 广播 SSE 事件 → 前端实时更新
  → 任务完成，前端拉取产物（markdown/srt/mindmap）
```

## 关键设计决策

- **Artifact-driven DAG**：每节点声明 requires/produces（artifact key），支持断点续传
- **EventBus + SSE**：内存广播，每个 task 的每个 SSE 客户端一个 asyncio.Queue
- **工厂模式**：ASR/LLM/下载器均通过工厂创建，支持多 provider
- **延迟导入**：torch/transformers/funasr 延迟导入，CPU-only 环境兼容
