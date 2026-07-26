"""speech_to_text.vad —— 长音频 VAD 静音切分。

设计依据：design D3 / spec speech-to-text「长音频 VAD 分段并行转录」/ CONTRACT §6.2。

为何按静音切而非固定窗口（design D3 Alternatives）：固定时长切片会从词句中间切断，
拼回后语义破碎；VAD 按静音切天然落在停顿处，不破坏词边界。

实现：复用镜像内已有的 ``ffmpeg``，用其 ``silencedetect`` 滤镜扫描静音边界，
随后按「目标段长（默认 ≤ 单次转写阈值）」在静音中点贪心选切点、再用 ``ffmpeg`` 抽
16kHz 单声道 WAV 分段。无额外依赖（torch / silero-vad 等不进 v1 镜像）。

分段与拼合对本模块调用方而言是底层细节；时间戳偏移拼回由 ``pipeline`` 完成。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

_LOGGER = logging.getLogger("speech_to_text.vad")

# silencedetect 输出正则
_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")

# 切片最小段长（秒），避免切成无意义碎片
_MIN_SEGMENT = 5.0


@dataclass
class AudioSegment:
    """一段待并行转录的音频切片。

    Attributes:
        start_offset: 该段在原音频中的起始秒（拼回时把段内 Cue 时间戳叠加此值）。
        duration: 该段时长（秒）。
        path: 抽出的临时 WAV 绝对路径。
    """

    start_offset: float
    duration: float
    path: str


def detect_silence_points(
    audio_path: str,
    noise_floor_db: float = -25.0,
    min_silence_sec: float = 0.6,
) -> list[tuple[float, float]]:
    """用 ffmpeg ``silencedetect`` 扫描静音区间。

    Returns:
        ``[(silence_start, silence_end), ...]`` 列表（秒）。ffmpeg 不可用或无静音返回 ``[]``。
    """
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats", "-i", audio_path,
                "-af", f"silencedetect=noise={noise_floor_db}dB:d={min_silence_sec}",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _LOGGER.warning("silencedetect 不可用，跳过 VAD：%s", e)
        return []
    stderr = proc.stderr or ""
    starts = [float(m) for m in _SILENCE_START_RE.findall(stderr)]
    ends = [float(m) for m in _SILENCE_END_RE.findall(stderr)]
    # 配对（ffmpeg 保证 start/end 交替出现）
    pairs: list[tuple[float, float]] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else s
        pairs.append((max(0.0, s), max(0.0, e)))
    return pairs


def compute_split_points(
    duration: float,
    silence_pairs: list[tuple[float, float]],
    max_segment_sec: float,
    target_segment_sec: Optional[float] = None,
) -> list[float]:
    """贪心选择切点（落在静音中点），使每段尽量接近目标、不超过上限。

    Returns:
        升序切点秒列表（不含 0 与 duration）；无合适切点时按 ``max_segment_sec`` 硬切兜底。
    """
    if duration <= max_segment_sec:
        return []
    target = target_segment_sec or (max_segment_sec * 0.8)
    # 静音中点候选
    candidates = [(s + e) / 2.0 for s, e in silence_pairs if e > s]

    points: list[float] = []
    cursor = 0.0
    ci = 0
    while duration - cursor > max_segment_sec:
        # 期望切点：当前 + target
        want = cursor + target
        # 在 [cursor + _MIN_SEGMENT, cursor + max_segment_sec] 内找最接近 want 的静音中点
        lo = cursor + _MIN_SEGMENT
        hi = cursor + max_segment_sec
        best: Optional[float] = None
        while ci < len(candidates) and candidates[ci] <= hi:
            if candidates[ci] >= lo:
                if best is None or abs(candidates[ci] - want) < abs(best - want):
                    best = candidates[ci]
            ci += 1
        if best is None:
            # 该区间无静音边界 → 硬切在 want（兜底，避免超阈值）
            best = min(want, hi)
        points.append(best)
        cursor = best
    return points


def _extract_segment(audio_path: str, start: float, end: float, out_path: str) -> bool:
    """``ffmpeg -ss <start> -t <dur>`` 抽 16kHz 单声道 WAV；成功 True。"""
    dur = max(0.0, end - start)
    if dur <= 0:
        return False
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", audio_path,
        "-ar", "16000", "-ac", "1", out_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _LOGGER.warning("抽取分段失败（start=%.2f）：%s", start, e)
        return False
    if proc.returncode != 0 or not os.path.exists(out_path):
        _LOGGER.warning("ffmpeg 抽段非零退出：%s", (proc.stderr or "").strip()[:200])
        return False
    return True


def split_audio_by_silence(
    audio_path: str,
    duration: float,
    work_dir: str,
    max_segment_sec: float = 300.0,
    target_segment_sec: Optional[float] = None,
    noise_floor_db: float = -25.0,
    min_silence_sec: float = 0.6,
) -> list[AudioSegment]:
    """按静音切分长音频为多个分段。

    Args:
        audio_path: 原音频绝对路径。
        duration: 原音频时长（秒）。
        work_dir: 临时分段落盘目录（由调用方管理生命周期）。
        max_segment_sec: 单段上限（默认 5 分钟，即单次转写阈值）。
        target_segment_sec: 单段目标时长（默认上限的 0.8）。

    Returns:
        按 ``start_offset`` 升序的 ``AudioSegment`` 列表；切分失败时回退为「整段」单元素列表
        （让 pipeline 退化为整段转录，优于整体失败）。
    """
    os.makedirs(work_dir, exist_ok=True)
    if duration <= max_segment_sec:
        return [AudioSegment(start_offset=0.0, duration=duration, path=audio_path)]

    silence_pairs = detect_silence_points(audio_path, noise_floor_db, min_silence_sec)
    split_points = compute_split_points(duration, silence_pairs, max_segment_sec, target_segment_sec)

    if not split_points:
        # 无需切分
        return [AudioSegment(start_offset=0.0, duration=duration, path=audio_path)]

    boundaries = [0.0, *split_points, duration]
    segments: list[AudioSegment] = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        if end - start < _MIN_SEGMENT and idx != 0:
            # 过短则并入上一段（调整上一段边界）
            if segments:
                prev = segments[-1]
                prev.duration = end - prev.start_offset
                continue
        out_path = os.path.join(work_dir, f"segment_{idx:04d}.wav")
        if not _extract_segment(audio_path, start, end, out_path):
            _LOGGER.warning("分段 %d 抽取失败，跳过（start=%.2f）", idx, start)
            continue
        segments.append(AudioSegment(start_offset=start, duration=end - start, path=out_path))

    if not segments:
        # 全部抽取失败 → 回退整段
        _LOGGER.warning("所有分段抽取失败，回退整段转录")
        return [AudioSegment(start_offset=0.0, duration=duration, path=audio_path)]
    _LOGGER.info("VAD 切分为 %d 段（总长 %.1fs）", len(segments), duration)
    return segments
