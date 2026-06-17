# Pipeline 流水线

## 6 节点线性 DAG

| 顺序 | 节点 | 输入 artifact | 输出 artifact | 进度阈值 |
|------|------|--------------|--------------|---------|
| 1 | DownloadNode | url (config) | video_file | 25% |
| 2 | ExtractAudioNode | video_file | audio_file | 45% |
| 3 | TranscribeNode | audio_file | srt_file | 70% |
| 4 | OrganizeNode | srt_file | markdown_file | 95% |
| 5 | MindmapNode | markdown_file | mindmap_file | 98% |
| 6 | CleanupNode | markdown_file | cleanup_manifest | 100% |

## Artifact 存储

```
data/tasks/<task_id>/artifacts/
  download_video_file
  extract_audio_audio_file
  transcribe_srt_file
  organize_markdown_file
  mindmap_mindmap_file
  cleanup_cleanup_manifest
```

## 断点续传

- 每节点执行前检查上游 artifact 是否存在
- 重跑某节点时，先删除该节点及下游所有 artifact
- `PipelineDAG.run(ctx, from_node=...)` 支持从指定节点重跑

## 节点状态

`pending → running → completed / failed`

失败节点的 error 信息存入 TaskRepository，前端可显示并触发重跑。

## CleanupNode 保留策略

按 `RetentionConfig`：
- `keep_video` (默认 False)：删除 video_file
- `keep_audio` (默认 False)：删除 audio_file
- `keep_srt` (默认 True)：保留 srt_file
- markdown/mindmap 始终保留
- 删除清单落盘到 cleanup_manifest
