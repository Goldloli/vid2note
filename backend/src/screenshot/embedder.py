"""截图嵌入纯函数实现（design D4 / task 4.8 / CONTRACT §6.3）。

职责：把笔记中 LLM 输出的 ``[IMG:<秒>]`` / ``[IMG:HH:MM:SS]`` 标记替换为真正的视频截帧图片。

工作流（design D4）：
  1. 笔记生成步骤（截图开关开启时）把字幕连同时间戳喂 LLM，指示其在「需图 / 重点画面」处输出 ``[IMG:HH:MM:SS]``；
  2. 本模块用正则扫标记，对每个**合法**时间戳调 ``ffmpeg -ss <ts> -i <video> -frames:v 1`` 截帧，落盘到截图目录；
  3. 把标记替换为 Markdown 图片引用（相对路径）；
  4. 非法时间戳 / 越界（超出视频时长）/ 截帧失败 → **静默跳过并记日志**，笔记**不残留**原始 ``[IMG:...]`` 标记。

本模块刻意**不依赖** DAG 上下文（``NodeContext``）与 ``DATA_ROOT``，只接收纯文本与路径，
便于用假视频 / monkeypatch ffmpeg 做单测（见 tests/test_screenshot.py）。
note 节点负责把 ``ctx`` 解析成绝对路径后调用本模块（见模块 ``__init__.py`` 的桥接说明）。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Final, List, Optional, Tuple, Union

# 内核 logger（design D6：从 core.kernel 取，不穿透内核内部）。
# try/except 双写仅为兼容内核尚未就绪的隔离单测环境；新增代码一律走 from src.xxx。
try:
    from src.core.kernel import logger as _default_logger
except ImportError:  # pragma: no cover - 仅在内核未装配的极端单测环境下触发
    _default_logger = logging.getLogger("screenshot")


# LLM 输出的图片标记：[IMG:120] / [IMG:01:30] / [IMG:01:02:03]。
# 内层用宽松的 [^]\n]* 框选任意内容（含非法形态如 [IMG:abc]、[IMG:]），
# 以便统一清洗——非法内容由 _parse_timestamp 判 None 后整标记移除，绝不残留。
_IMG_MARK_RE: Final[re.Pattern] = re.compile(r"\[IMG:([^]\n]*)\]")

# ffmpeg 可执行名；单测可 monkeypatch 改写（或直接替换 capture_frame）。
FFMPEG: str = "ffmpeg"

# 截图文件名模板（确定性命名：同一秒数 → 同一文件，天然去重）。
_SCREENSHOT_NAME: Final[str] = "shot_{seconds}.png"

# Markdown 图片引用的 alt 文本（中文，符合语言约定）。
_IMG_ALT: Final[str] = "截图"


def _parse_timestamp(raw: str) -> Optional[int]:
    """把标记内的时间串解释为整数秒；非法返回 None。

    支持三种 LLM 可能输出的形态：
      - 纯秒：``120`` → 120
      - 分秒：``01:30`` / ``1:30`` → 90
      - 时分秒：``01:02:03`` → 3723

    校验规则：每段须为纯数字（拒绝负数 / 小数 / 空段）；段数 ≤ 3；
    当存在更高位时，秒位、分位必须 < 60。任一不满足返回 None。
    """
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) > 3:
        return None
    # isdigit 拒绝负号、小数点、空串与Unicode数字外的字符
    if not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    seconds = nums[-1]
    # 存在更高位（分/时）时，秒位必须 < 60
    if len(nums) > 1 and seconds >= 60:
        return None
    if len(nums) >= 2:
        minutes = nums[-2]
        # 存在时位时，分位也必须 < 60
        if len(nums) == 3 and minutes >= 60:
            return None
        seconds += minutes * 60
    if len(nums) == 3:
        seconds += nums[0] * 3600
    return seconds if seconds >= 0 else None


def parse_img_marks(markdown_text: str) -> List[int]:
    """正则扫描 LLM 输出的 ``[IMG:<秒>]`` 标记，返回合法秒数列表。

    - 只返回能成功解释为秒数的标记（非法时间戳被忽略）。
    - 去重并**按首次出现顺序**返回（同一秒数只截一帧）。

    对应 CONTRACT §6.3 ``parse_img_marks``。
    """
    seen: set[int] = set()
    result: List[int] = []
    for m in _IMG_MARK_RE.finditer(markdown_text or ""):
        ts = _parse_timestamp(m.group(1))
        if ts is None or ts in seen:
            continue
        seen.add(ts)
        result.append(ts)
    return result


def capture_frame(video_abs_path: str, ts_seconds: int, out_abs_path: str) -> bool:
    """``ffmpeg -ss <ts> -i <video> -frames:v 1`` 截单帧；成功 True，失败 False。

    - ``-ss`` 置于 ``-i`` 之前 = 输入级快进（快且精确），``-frames:v 1`` = 仅输出一帧。
    - 成功判据：返回码 0 **且**输出文件存在**且**非空。越界时间戳（超出视频时长）会让
      ffmpeg 产出空文件 / 非零退出，从而被判定失败 —— 因此「越界跳过」无需额外探测时长。
    - 任何异常（视频缺失 / ffmpeg 缺失 / 非零退出）一律返回 False，**不抛出**（design D4 容错）。
    """
    try:
        if ts_seconds < 0:
            return False
        out = Path(out_abs_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            FFMPEG, "-y", "-loglevel", "error",
            "-ss", str(int(ts_seconds)),
            "-i", str(video_abs_path),
            "-frames:v", "1",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True)  # noqa: S603 - 命令由常量+受控参数构成
        return proc.returncode == 0 and out.is_file() and out.stat().st_size > 0
    except Exception:  # noqa: BLE001 - design D4：截帧失败静默降级，绝不向上抛
        return False


def embed_screenshots(
    markdown_text: str,
    video_path: Optional[Union[str, Path]],
    screenshots_dir: Union[str, Path],
    *,
    image_rel_from: Optional[Union[str, Path]] = None,
    logger: Optional[logging.Logger] = _default_logger,
) -> Tuple[str, List[str]]:
    """扫描并替换 ``[IMG:...]`` 标记为 Markdown 图片语法（design D4 / task 4.8）。

    逐标记处理：
      - 解析时间戳；**解析失败** → 静默移除标记（不残留原始 ``[IMG:...]``）。
      - 用 ffmpeg 在 ``video_path`` 的该秒处截帧，落 ``screenshots_dir/shot_<秒>.png``。
      - **截帧成功** → 替换为 ``![截图](<相对路径>)``；**失败**（含越界 / ffmpeg 不可用）→ 静默移除标记。
    同一秒数只截一次（文件名确定性 ``shot_<秒>.png``），重复标记复用同一文件与同一图片引用。
    越界 / 无效 / 截帧失败均只记日志、不抛出；单标记失败不中断整体（spec note-generation 场景 188）。

    参数：
      markdown_text: 含 ``[IMG:...]`` 标记的笔记原文（``None`` 视为空串）。
      video_path: 视频文件绝对路径；``None`` 或文件不存在 → **所有标记被移除**（不截帧），
        适用于截图开关关、或视频已过期 / local_audio 等无视频场景。
      screenshots_dir: 截图落盘目录（截帧前自动创建）。
      image_rel_from: Markdown 图片 ``src`` 的相对基准目录（通常 = 笔记所在目录，
        如 ``<DATA_ROOT>/notes/<task_id>``）。``None`` → 图片 ``src`` 用纯文件名
        （适合截图与笔记同目录的场景）。无论何种取值，均输出 POSIX 风格相对路径。
      logger: 日志器，默认取内核 logger。

    返回：
      ``(清洗后 markdown, 图片 src 列表)``。列表元素**与写入 markdown 的 src 完全一致**，
      按「首次成功截帧」顺序排列。调用方（note 节点）据此再换算成 ``DATA_ROOT`` 相对路径登记产物。

    note 节点桥接（CONTRACT §6.3 的 ctx 形态 → 本纯函数）::

        md, srcs = embed_screenshots(
            markdown_text=md,
            video_path=str(ctx.data_root / video_rel) if video_rel else None,
            screenshots_dir=ctx.product_path("screenshot", "png").parent,
            image_rel_from=ctx.data_root / "notes" / ctx.task_id,
        )
        # srcs 形如 ["../../screenshots/<tid>/shot_120.png", ...]
        # 换算 DATA_ROOT 相对路径登记：rel = os.path.relpath(note_dir/src, data_root)
    """
    text = markdown_text or ""
    shots_dir = Path(screenshots_dir)
    video_abs = str(video_path) if video_path else ""
    video_ok = bool(video_abs) and Path(video_abs).is_file()
    if not video_ok and logger is not None:
        logger.warning("截图嵌入跳过：视频路径无效或文件不存在 (%r)", video_abs or video_path)

    # 秒数 -> 完整图片 markdown（仅成功截帧才写入）；同一秒数复用同一文件与引用
    captured: dict[int, str] = {}
    produced_srcs: List[str] = []  # 首次成功截帧顺序

    def _src_for(seconds: int) -> str:
        fname = _SCREENSHOT_NAME.format(seconds=seconds)
        if image_rel_from is None:
            return fname
        rel = os.path.relpath(shots_dir / fname, str(image_rel_from))
        return Path(rel).as_posix()

    def _replace(match: re.Match) -> str:
        raw = match.group(1)
        ts = _parse_timestamp(raw)
        if ts is None:
            if logger is not None:
                logger.warning("截图标记时间戳非法，已移除：[IMG:%s]", raw)
            return ""
        if not video_ok:
            return ""  # 无可用视频：仅清除标记，不截帧
        if ts in captured:
            return captured[ts]
        out = shots_dir / _SCREENSHOT_NAME.format(seconds=ts)
        if not capture_frame(video_abs, ts, str(out)):
            if logger is not None:
                logger.warning("截帧失败或时间戳越界，已跳过：[IMG:%s] → %s", raw, out)
            return ""
        src = _src_for(ts)
        markdown_img = f"![{_IMG_ALT}]({src})"
        captured[ts] = markdown_img
        produced_srcs.append(src)
        return markdown_img

    cleaned = _IMG_MARK_RE.sub(_replace, text)
    return cleaned, produced_srcs
