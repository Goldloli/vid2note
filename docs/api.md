# API 文档

## 基础信息

- Base URL: `http://localhost:8000/api/v1`
- 所有响应格式: `ApiResponse<T>`

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": null
}
```

## 任务管理

### 创建任务

```http
POST /tasks
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=xxx",
  "mode": "full"
}
```

响应:
```json
{
  "success": true,
  "data": {
    "task_id": "task_a1b2c3d4e5f6",
    "status": "pending",
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

### 获取任务详情

```http
GET /tasks/{task_id}
```

### 获取任务列表

```http
GET /tasks?page=1&limit=20
```

### 重跑节点

```http
POST /tasks/{task_id}/nodes/{node_name}/retry
```

### SSE 进度推送

```http
GET /tasks/{task_id}/events
```

EventSource 连接，实时推送节点状态变化。

## 文件上传

```http
POST /upload
Content-Type: multipart/form-data

file: <视频文件>
```

## 配置

```http
GET /config
PUT /config
```

## 健康检查

```http
GET /health
```

响应:
```json
{
  "success": true,
  "data": {
    "status": "ok",
    "version": "0.1.0"
  }
}
```
