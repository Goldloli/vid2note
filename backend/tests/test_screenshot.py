"""src/screenshot 截图嵌入单测（design D4 / task 4.8 / CONTRACT §6.3）。

覆盖：
  - parse_img_marks：纯秒 / MM:SS / HH:MM:SS / 非法 / 去重。
  - capture_frame：monkeypatch subprocess 的成功 / 失败 / 越界 / 异常路径。
  - embed_screenshots：标记替换、无效移除、不残留、去重复用、video_path=None 清空、
    image_rel_from 相对路径、单标记失败不中断；并含一条真实 ffmpeg 集成用例。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.screenshot import embed_screenshots, capture_frame, parse_img_marks
from src.screenshot import embedder


# ----------------------------- parse_img_marks ----------------------------- #

def test_parse_seconds_forms():
    assert parse_img_marks("前 [IMG:120] 中 [IMG:01:30] 后") == [120, 90]
    assert parse_img_marks("[IMG:01:02:03]") == [3723]
    assert parse_img_marks("[IMG:0]") == [0]


def test_parse_dedup_keeps_first_order():
    md = "[IMG:300] a [IMG:90] b [IMG:300] c [IMG:90]"
    assert parse_img_marks(md) == [300, 90]


def test_parse_invalid_skipped():
    # 非法：空、非数字、秒位越界(有分位)、段数过多
    assert parse_img_marks("[IMG:] [IMG:abc] [IMG:1:90] [IMG:1:2:3:4]") == []
    # 但纯秒可以是任意大整数（小时级视频）
    assert parse_img_marks("[IMG:3600]") == [3600]
    # 分位单独存在(两段)允许 >=60 吗？两段=MM:SS，分位无上限约束
    assert parse_img_marks("[IMG:90:05]") == [90 * 60 + 5]


def test_parse_none_or_empty():
    assert parse_img_marks("") == []
    assert parse_img_marks(None) == []  # type: ignore[arg-type]
    assert parse_img_marks("无标记的普通笔记") == []


# ----------------------------- capture_frame ----------------------------- #

class _FakeProc:
    def __init__(self, returncode=0):
        self.returncode = returncode


def test_capture_frame_success(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "out" / "shot_10.png"

    def fake_run(cmd, capture_output):
        # 模拟 ffmpeg 写出非空 PNG
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n")
        return _FakeProc(0)

    monkeypatch.setattr(embedder.subprocess, "run", fake_run)
    assert capture_frame(str(video), 10, str(out)) is True
    assert out.is_file() and out.stat().st_size > 0


def test_capture_frame_nonzero_returncode(monkeypatch, tmp_path):
    out = tmp_path / "shot_10.png"
    monkeypatch.setattr(embedder.subprocess, "run", lambda cmd, capture_output: _FakeProc(1))
    # 输出文件不存在 → False
    assert capture_frame(str(tmp_path / "v.mp4"), 10, str(out)) is False


def test_capture_frame_empty_output_is_failure(monkeypatch, tmp_path):
    """越界时间戳场景：ffmpeg 返回 0 但产出空文件 → 判失败。"""
    out = tmp_path / "shot_999.png"

    def fake_run(cmd, capture_output):
        Path(cmd[-1]).write_bytes(b"")  # 空文件
        return _FakeProc(0)

    monkeypatch.setattr(embedder.subprocess, "run", fake_run)
    assert capture_frame(str(tmp_path / "v.mp4"), 999, str(out)) is False


def test_capture_frame_exception_is_false(monkeypatch, tmp_path):
    def boom(cmd, capture_output):
        raise FileNotFoundError("ffmpeg missing")

    monkeypatch.setattr(embedder.subprocess, "run", boom)
    assert capture_frame(str(tmp_path / "v.mp4"), 5, str(tmp_path / "x.png")) is False


def test_capture_frame_negative_ts(tmp_path):
    assert capture_frame(str(tmp_path / "v.mp4"), -1, str(tmp_path / "x.png")) is False


# ----------------------------- embed_screenshots ----------------------------- #

def _stub_capture_that_writes(monkeypatch):
    """让 capture_frame 总成功并写出非空占位文件。"""
    def fake(video, ts, out):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"\x89PNG")
        return True
    monkeypatch.setattr(embedder, "capture_frame", fake)


@pytest.fixture
def video_file(tmp_path):
    """一个占位视频文件（有内容即可，使 embed_screenshots 的 video_ok 判定为真）。"""
    p = tmp_path / "v.mp4"
    p.write_bytes(b"fake-video-bytes")
    return p


def test_embed_replaces_valid_marks(monkeypatch, video_file, tmp_path):
    _stub_capture_that_writes(monkeypatch)
    md = "开头\n\n[IMG:120]\n\n中段 [IMG:01:30] 结尾"
    shots = tmp_path / "shots"
    cleaned, srcs = embed_screenshots(md, str(video_file), shots,
                                      image_rel_from=tmp_path)
    # 两个标记都被替换为图片，无残留 [IMG:
    assert "[IMG:" not in cleaned
    # screenshots_dir=shots，相对 tmp_path → shots/shot_*.png
    assert "![截图](shots/shot_120.png)" in cleaned
    assert "![截图](shots/shot_90.png)" in cleaned
    assert srcs == ["shots/shot_120.png", "shots/shot_90.png"]
    # 文件确实落盘
    assert (shots / "shot_120.png").is_file()
    assert (shots / "shot_90.png").is_file()


def test_embed_relative_path_via_image_rel_from(monkeypatch, video_file, tmp_path):
    _stub_capture_that_writes(monkeypatch)
    data_root = tmp_path
    note_dir = data_root / "notes" / "task_abc"
    shots_dir = data_root / "screenshots" / "task_abc"
    note_dir.mkdir(parents=True)
    md = "[IMG:5]"
    cleaned, srcs = embed_screenshots(md, str(video_file), shots_dir,
                                      image_rel_from=note_dir)
    # 相对笔记目录：../../screenshots/task_abc/shot_5.png
    assert srcs == ["../../screenshots/task_abc/shot_5.png"]
    assert "![截图](../../screenshots/task_abc/shot_5.png)" in cleaned


def test_embed_invalid_mark_removed_no_residue(monkeypatch, video_file, tmp_path):
    _stub_capture_that_writes(monkeypatch)
    md = "前 [IMG:1:90] 后 [IMG:abc] 尾"  # 两个都非法
    cleaned, srcs = embed_screenshots(md, str(video_file), tmp_path / "shots")
    assert "[IMG:" not in cleaned
    assert srcs == []
    assert "![截图]" not in cleaned


def test_embed_capture_failure_skips_mark(monkeypatch, video_file, tmp_path):
    # video 存在但 capture_frame 总失败（模拟越界 / ffmpeg 不可用）
    monkeypatch.setattr(embedder, "capture_frame", lambda v, t, o: False)
    md = "[IMG:99999] 残留测试"
    cleaned, srcs = embed_screenshots(md, str(video_file), tmp_path / "shots")
    assert "[IMG:" not in cleaned           # 不残留原始标记
    assert "![截图]" not in cleaned          # 也不插入失败图片
    assert srcs == []


def test_embed_single_failure_does_not_break_others(monkeypatch, video_file, tmp_path):
    # 只有 ts=999 失败，ts=10 成功
    def selective(video, ts, out):
        if ts == 999:
            return False
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"\x89PNG")
        return True
    monkeypatch.setattr(embedder, "capture_frame", selective)
    md = "[IMG:999] [IMG:10]"
    cleaned, srcs = embed_screenshots(md, str(video_file), tmp_path / "shots",
                                      image_rel_from=None)
    assert "[IMG:" not in cleaned
    assert "![截图](shot_10.png)" in cleaned
    assert srcs == ["shot_10.png"]


def test_embed_duplicate_ts_reuses_one_file(monkeypatch, video_file, tmp_path):
    calls = []
    def fake(video, ts, out):
        calls.append(ts)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"\x89PNG")
        return True
    monkeypatch.setattr(embedder, "capture_frame", fake)
    md = "[IMG:42] ... [IMG:42] ... [IMG:42]"
    cleaned, srcs = embed_screenshots(md, str(video_file), tmp_path / "shots")
    assert calls == [42]                       # 只截一次
    assert cleaned.count("![截图](shot_42.png)") == 3
    assert srcs == ["shot_42.png"]


def test_embed_no_video_clears_all_marks(monkeypatch, tmp_path):
    _stub_capture_that_writes(monkeypatch)  # 即便 stub 存在，无视频也不应调用
    md = "[IMG:10] [IMG:20]"
    # video_path=None
    cleaned, srcs = embed_screenshots(md, None, tmp_path / "shots")
    assert "[IMG:" not in cleaned
    assert srcs == []
    # 不存在的视频路径同理
    cleaned2, srcs2 = embed_screenshots(md, str(tmp_path / "missing.mp4"), tmp_path / "shots")
    assert "[IMG:" not in cleaned2
    assert srcs2 == []


def test_embed_no_marks_passthrough(monkeypatch, tmp_path):
    _stub_capture_that_writes(monkeypatch)
    md = "完全没有任何标记的笔记正文。"
    cleaned, srcs = embed_screenshots(md, str(tmp_path / "v.mp4"), tmp_path / "shots")
    assert cleaned == md
    assert srcs == []


def test_embed_none_text(tmp_path):
    cleaned, srcs = embed_screenshots(None, None, tmp_path / "shots")  # type: ignore[arg-type]
    assert cleaned == ""
    assert srcs == []


# ----------------------------- 真实 ffmpeg 集成 ----------------------------- #

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not HAS_FFMPEG, reason="本机无 ffmpeg，跳过真实截帧集成")
def test_capture_frame_real_ffmpeg(tmp_path):
    """用 ffmpeg 生成 3 秒的纯色测试视频，验证在第 1 秒真实截帧成功、越界秒失败。"""
    video = tmp_path / "testsrc.mp4"
    # 生成 3 秒、640x480 纯色测试源（testsrc2），无音频，快且确定性
    gen = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=10",
         "-t", "3", str(video)],
        capture_output=True,
    )
    assert gen.returncode == 0 and video.is_file(), "测试视频生成失败"

    ok_out = tmp_path / "ok.png"
    assert capture_frame(str(video), 1, str(ok_out)) is True
    assert ok_out.is_file() and ok_out.stat().st_size > 100  # 真实 PNG 有体积

    # 越界：第 99 秒（视频只有 3 秒）→ 失败
    oob_out = tmp_path / "oob.png"
    assert capture_frame(str(video), 99, str(oob_out)) is False


@pytest.mark.skipif(not HAS_FFMPEG, reason="本机无 ffmpeg，跳过端到端集成")
def test_embed_screenshots_real_ffmpeg(tmp_path):
    """端到端：生成真实视频 → embed_screenshots 替换标记 → 图片落盘且可被引用。"""
    video = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10", "-t", "5", str(video)],
        capture_output=True, check=True,
    )
    md = "# 笔记\n\n重点画面 [IMG:2] 此处需图\n\n另一处 [IMG:99] 越界\n"
    shots = tmp_path / "screenshots" / "task_x"
    note_dir = tmp_path / "notes" / "task_x"
    note_dir.mkdir(parents=True)
    cleaned, srcs = embed_screenshots(md, str(video), shots, image_rel_from=note_dir)
    assert "[IMG:" not in cleaned
    # 合法 ts=2 成功；越界 ts=99 被跳过
    assert any("shot_2.png" in s for s in srcs)
    assert all("shot_99" not in s for s in srcs)
    assert (shots / "shot_2.png").is_file()
    assert not (shots / "shot_99.png").is_file()
