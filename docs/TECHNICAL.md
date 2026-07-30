# 技术文档

本文件原先记录的是重构前接口，现拆分为以下维护中的文档：

- [架构与扩展点](ARCHITECTURE.md)
- [配置与数据](CONFIGURATION.md)
- [故障排查](TROUBLESHOOTING.md)
- [Roadmap](ROADMAP.md)
- [后端契约](../backend/CONTRACT.md)
- [OpenSpec 当前规格](../openspec/specs/)

运行时权威入口是 `/api/v1`，Docker 宿主端口默认为 `8761`，后端容器端口为 `8765`。
