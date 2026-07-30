# 故障排查

## 页面打不开

```bash
docker compose ps
docker compose logs --tail=200 vid2note
curl -v http://localhost:8761/api/v1/health
```

确认没有修改 `VID2NOTE_PORT`，并检查端口是否被其他程序占用。

## 容器无法写入 data

Linux 上把 `.env` 的 UID/GID 设置为当前用户：

```bash
printf 'VID2NOTE_UID=%s\nVID2NOTE_GID=%s\n' "$(id -u)" "$(id -g)"
```

请手动把结果合并到 `.env`，然后运行：

```bash
docker compose build --no-cache
docker compose up -d
```

不要把 `data/` 改成所有用户可写。

## LLM 提示未配置 Key

- 如果通过设置页配置，确认保存后创建的是新任务。
- 如果通过 `.env` 配置，运行 `docker compose up -d --build` 让环境变量进入容器。
- `data/config/settings.json` 已保存的 Provider/模型优先于 `.env`；可在设置页重新保存。
- 查看日志时不要粘贴或公开真实 Key。

## 密钥显示“密文损坏”或“主密钥错误”

- `credentials.enc` 必须配合创建它的同一把主密钥使用；
- 检查 `VID2NOTE_MASTER_KEY_FILE` 是否挂载到容器内且可读；
- 若从备份恢复，确认同时恢复了 `credentials.enc` 与对应的 `master.key`；
- 不要手工编辑密文文件。可在保留备份后，通过设置页清除并重新填写单个凭证。

自动生成的文件应为 `0600`。Linux 上可检查：

```bash
docker compose exec vid2note ls -l /app/data/config
```

## 设置文件损坏

应用会尝试读取 `data/config/settings.json.last-good`。先停止容器并备份 `data/config/`，确认 last-good 内容有效后再人工恢复；不要在服务运行时直接覆盖设置文件。

## Ollama 无法连接

宿主机检查：

```bash
ollama list
curl http://localhost:11434/api/tags
```

容器中检查：

```bash
docker compose exec vid2note curl http://host.docker.internal:11434/api/tags
```

模型名必须与 `ollama list` 完全一致。新安装默认使用 `qwen3.5`，你也可以填写已安装的任意模型。Linux 已通过 Compose 添加 host-gateway；自定义 Docker 网络时需要保留该映射。

## 本地 Whisper 显示 not ready

- 模型必须已经存在，应用不会自动下载。
- 设置页填写的是容器内路径，不是宿主机路径。
- 用 `docker compose exec vid2note ls -la /models` 确认挂载。
- faster-whisper 使用模型目录；whisper.cpp 使用模型文件并需要可执行的 CLI。

## 线上 ASR 不可用

`bcut` 是依赖外部服务的实验性在线兼容能力，不保证持续可用。可以：

- 在 ASR 页运行就绪测试；
- 配置本地 Whisper；
- 配置自己的外部 ASR endpoint；
- 查看任务日志中的结构化降级原因。

## Bilibili 下载失败

可能原因包括登录限制、风控、地区限制和 Cookie 失效。重新配置 Cookie，并确认你有权下载相关内容。不要在 Issue 中粘贴 Cookie 或私人链接。

## PDF 解析失败

当前只支持带可提取文字层的常规 PDF。扫描件、加密 PDF、损坏文件和复杂多栏排版可能无法正确解析。OCR 和 MinerU 结构化解析在 Roadmap 中。

## 清空全部本地数据

这会删除任务历史、公开设置、主密钥、加密凭证和产物。先备份，然后在容器停止时自行移走整个 `data/` 内容。不要在服务运行中直接删除 SQLite 或配置文件。
