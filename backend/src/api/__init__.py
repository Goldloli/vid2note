"""API 包。

稳定入口是 :mod:`src.api.v1`。这里保持无副作用，避免仅导入 v1 路由时加载
旧版上传/配置路由并在磁盘生成遗留 ``config.yaml``。
"""

__all__: list[str] = []
