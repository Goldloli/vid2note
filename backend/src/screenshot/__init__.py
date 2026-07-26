"""截图嵌入模块（design D4 / task 4.8 / CONTRACT §6.3）。

对外暴露三个**纯函数**，不依赖 DAG 上下文（``NodeContext``）与 ``DATA_ROOT``，
便于用假视频 / monkeypatch ffmpeg 做单测：

  - :func:`parse_img_marks`：正则扫描 ``[IMG:<秒>]`` 标记 → 合法秒数列表。
  - :func:`capture_frame`：``ffmpeg -ss <ts> -i <video> -frames:v 1`` 截单帧 → 成功与否。
  - :func:`embed_screenshots`：完整流程，逐标记截帧并替换为 Markdown 图片语法。

与 CONTRACT §6.3 的对接
------------------------
CONTRACT §6.3 把 ``embed_screenshots`` 写成 ctx 形态
``embed_screenshots(ctx, markdown_text, srt_rel_path, video_rel_path)``。
本模块**有意**把 ctx 解耦为纯路径参数（``embed_screenshots(markdown_text, video_path,
screenshots_dir, ...)``），使核心逻辑可单测；note 节点按如下桥接即可满足契约 ::

    from src.screenshot import embed_screenshots
    video_abs = str(ctx.data_root / video_rel) if video_rel else None
    shots_dir = ctx.product_path("screenshot", "png").parent   # <DATA_ROOT>/screenshots/<tid>/
    note_dir  = ctx.data_root / "notes" / ctx.task_id           # 笔记所在目录
    md, srcs = embed_screenshots(md, video_abs, shots_dir, image_rel_from=note_dir)
    # md 内图片 src 形如 ../../screenshots/<tid>/shot_120.png（相对笔记，md 可移植）
    # 登记 DATA_ROOT 相对路径：
    for src in srcs:
        rel = os.path.relpath(str(note_dir / src), str(ctx.data_root))
        ctx.register_product("screenshot", rel, (note_dir / src).stat().st_size)
"""

from .embedder import (
    FFMPEG,
    capture_frame,
    embed_screenshots,
    parse_img_marks,
)

__all__ = [
    "parse_img_marks",
    "capture_frame",
    "embed_screenshots",
    "FFMPEG",
]
