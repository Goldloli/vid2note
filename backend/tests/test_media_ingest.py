"""media_ingest 模块测试（task 2.1-2.5 / spec media-ingest）。

覆盖：
- 来源识别五类 + 拒绝场景（纯函数，无外部依赖）
- 失败归类（消息文本 → 五种 kind）
- Bilibili cookie：完整登录态注入 / 部分缺失降级 / 不外泄到其它来源
- 取消信号（progress hook 抛 IngestCancelled）
- 工具缺失（yt-dlp / ffmpeg 缺失归类）
- ffmpeg 提取：含音轨成功、无音轨报错且不留半成品（真实 ffmpeg，无网络）

真实 ffmpeg 的用例在本机 / 容器内均可用（task 9.1 保证镜像内置 ffmpeg）；
未装 ffmpeg 时自动 skip，不影响其余纯逻辑用例。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.media_ingest import (
    SourceType,
    UploadedFile,
    identify_source,
    download_video,
    extract_audio,
    DownloadError,
    ExtractError,
    IngestCancelled,
    DOWNLOAD_ERR_INVALID_URL,
    DOWNLOAD_ERR_NEEDS_LOGIN,
    DOWNLOAD_ERR_NETWORK,
    DOWNLOAD_ERR_RISK_CONTROL,
    DOWNLOAD_ERR_TOOL_MISSING,
)
from src.media_ingest import downloader as dl
from src.media_ingest import audio as aud


# --------------------------------------------------------------------------- #
# 测试桩：最小 NodeContext
# --------------------------------------------------------------------------- #
class _NoCancel:
    def is_cancelled(self):
        return False


class _FakeCtx:
    """最小可用的 NodeContext 桩：产物按 CONTRACT §2.1 目录布局（audio/srt 单数）。"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.work_temp = data_root / "temp" / "task_t1"
        self.work_temp.mkdir(parents=True, exist_ok=True)
        self.products = []
        self.logs = []
        self.progress = []
        self.cancel = _NoCancel()

    # kind → 目录名映射（NodeContext 的职责；此处按 §2.1 复刻）
    _DIR = {"video": "videos", "audio": "audio", "srt": "srt",
            "note": "notes", "screenshot": "screenshots"}

    def product_path(self, kind: str, ext: str) -> Path:
        p = self.data_root / self._DIR[kind] / "task_t1" / f"task_t1.{ext}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def register_product(self, kind, rel, size):
        self.products.append((kind, rel, size))

    def emit_progress(self, pct, msg=None):
        self.progress.append((pct, msg))

    def emit_log(self, level, line):
        self.logs.append((level, line))


# --------------------------------------------------------------------------- #
# identify_source：五类来源 + 拒绝
# --------------------------------------------------------------------------- #
class TestIdentifySource:
    def test_youtube_variants(self):
        assert identify_source("https://www.youtube.com/watch?v=abc", None) == SourceType.YOUTUBE
        assert identify_source("https://youtu.be/abc", None) == SourceType.YOUTUBE
        assert identify_source("https://m.youtube.com/shorts/xyz", None) == SourceType.YOUTUBE

    def test_bilibili_variants(self):
        assert identify_source("https://www.bilibili.com/video/BV1xx", None) == SourceType.BILIBILI
        assert identify_source("https://b23.tv/abc", None) == SourceType.BILIBILI

    def test_direct_link(self):
        assert identify_source("https://example.com/clip.mp4", None) == SourceType.DIRECT

    def test_local_video_by_ext_and_mime(self):
        assert identify_source(None, UploadedFile("/p/a", "clip.mp4", "video/mp4", 1)) == SourceType.LOCAL_VIDEO
        # 扩展名缺失时退到 MIME 前缀
        assert identify_source(None, UploadedFile("/p/a", "noext", "video/webm", 1)) == SourceType.LOCAL_VIDEO

    def test_local_audio_by_ext_and_mime(self):
        assert identify_source(None, UploadedFile("/p/a", "song.m4a", "audio/mp4", 1)) == SourceType.LOCAL_AUDIO
        assert identify_source(None, UploadedFile("/p/a", "noext", "audio/flac", 1)) == SourceType.LOCAL_AUDIO

    @pytest.mark.parametrize("url,uploaded", [
        ("", None),                                    # 空
        (None, None),                                  # 全空
        ("plain text without url", None),              # 纯文本
        ("ftp://example.com/x", None),                 # 不支持协议
        (None, UploadedFile("/p/a", "doc.pdf", "application/pdf", 1)),  # 不支持的本地类型
    ])
    def test_rejected_sources(self, url, uploaded):
        with pytest.raises(ValueError, match="无法识别的媒体来源"):
            identify_source(url, uploaded)

    def test_uploaded_takes_precedence_over_url(self):
        # 同时给了链接和文件 → 按文件类型走
        assert identify_source("https://youtube.com/x",
                               UploadedFile("/p/a", "c.mp4", "video/mp4", 1)) == SourceType.LOCAL_VIDEO


# --------------------------------------------------------------------------- #
# 失败归类
# --------------------------------------------------------------------------- #
class TestClassify:
    @pytest.mark.parametrize("msg,kind", [
        ("Video unavailable", DOWNLOAD_ERR_INVALID_URL),
        ("HTTP Error 404: Not Found", DOWNLOAD_ERR_INVALID_URL),
        ("video does not exist", DOWNLOAD_ERR_INVALID_URL),
        ("is not a valid URL", DOWNLOAD_ERR_INVALID_URL),
        ("unsupported url", DOWNLOAD_ERR_INVALID_URL),
    ])
    def test_invalid_url(self, msg, kind):
        assert dl._classify_download_error(Exception(msg)) == kind

    @pytest.mark.parametrize("msg,kind", [
        ("Sign in to confirm you're not a bot", DOWNLOAD_ERR_RISK_CONTROL),
        ("Captcha required", DOWNLOAD_ERR_RISK_CONTROL),
        ("HTTP Error 429 Too Many Requests", DOWNLOAD_ERR_RISK_CONTROL),
    ])
    def test_risk_control(self, msg, kind):
        assert dl._classify_download_error(Exception(msg)) == kind

    @pytest.mark.parametrize("msg,kind", [
        ("This video is available to this user only", DOWNLOAD_ERR_NEEDS_LOGIN),
        ("Join this channel to get access", DOWNLOAD_ERR_NEEDS_LOGIN),
        ("members-only content", DOWNLOAD_ERR_NEEDS_LOGIN),
        ("需要登录", DOWNLOAD_ERR_NEEDS_LOGIN),
    ])
    def test_needs_login(self, msg, kind):
        assert dl._classify_download_error(Exception(msg)) == kind

    def test_network_exception_type(self):
        # 沿异常链识别网络异常类型
        try:
            raise ConnectionError("x")
        except ConnectionError as e:
            assert dl._classify_download_error(e) == DOWNLOAD_ERR_NETWORK
        try:
            raise TimeoutError("x")
        except TimeoutError as e:
            assert dl._classify_download_error(e) == DOWNLOAD_ERR_NETWORK

    def test_network_message(self):
        assert dl._classify_download_error(
            Exception("Connection timed out")) == DOWNLOAD_ERR_NETWORK

    def test_none_is_invalid_url(self):
        assert dl._classify_download_error(None) == DOWNLOAD_ERR_INVALID_URL


# --------------------------------------------------------------------------- #
# Bilibili cookie 工具
# --------------------------------------------------------------------------- #
class TestBilibiliCookies:
    _FULL = {"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "d"}

    def test_usable_when_all_three_present(self):
        assert dl._bilibili_cookies_usable(self._FULL) is True

    @pytest.mark.parametrize("cookies", [
        None,
        {},
        {"SESSDATA": "s"},                                 # 仅一项
        {"SESSDATA": "s", "bili_jct": "j"},                # 缺 DedeUserID
        {"SESSDATA": "", "bili_jct": "j", "DedeUserID": "d"},  # 一项空
    ])
    def test_not_usable(self, cookies):
        assert dl._bilibili_cookies_usable(cookies) is False

    def test_filter_strips_extra_keys(self):
        cookies = {"SESSDATA": " s ", "bili_jct": "j", "DedeUserID": "d",
                   "extra_key": "should_be_dropped"}
        filtered = dl._filter_bilibili_cookies(cookies)
        assert set(filtered.keys()) == {"SESSDATA", "bili_jct", "DedeUserID"}
        assert filtered["SESSDATA"] == "s"  # 去空白

    def test_filter_empty(self):
        assert dl._filter_bilibili_cookies(None) == {}


# --------------------------------------------------------------------------- #
# download_video：cookie 注入 / 不外泄 / 降级（用 fake yt-dlp，无网络）
# --------------------------------------------------------------------------- #
class TestDownloadCookiePolicy:
    @staticmethod
    def _patch_tools(monkeypatch, fake_module):
        monkeypatch.setattr(dl, "_require_yt_dlp", lambda: fake_module)
        monkeypatch.setattr(dl, "_require_ffmpeg", lambda: None)

    def _fake_module(self, behavior):
        """构造假 yt_dlp 模块：behavior(opts, urls) 控制每次 download 行为。"""
        captured = []

        class _FakeYDL:
            def __init__(self, opts):
                self.opts = opts
                captured.append(opts)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def download(self, urls):
                behavior(self.opts, urls)

        return types.SimpleNamespace(YoutubeDL=_FakeYDL), captured

    def test_youtube_never_attaches_bilibili_cookie(self, monkeypatch, tmp_path):
        # fake download 直接返回（不产出文件 → 最终 DownloadError），仅用于捕 opts
        fake, captured = self._fake_module(lambda o, u: None)
        self._patch_tools(monkeypatch, fake)
        ctx = _FakeCtx(tmp_path)
        bili_cookies = {"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "d"}

        with pytest.raises(DownloadError):
            download_video(ctx, "https://youtube.com/watch?v=x",
                           SourceType.YOUTUBE, bili_cookies)

        assert captured, "应至少发起一次下载"
        assert "cookies" not in captured[0], "YouTube 来源 MUST NOT 附带 bilibili cookie"

    def test_bilibili_injects_filtered_cookies(self, monkeypatch, tmp_path):
        fake, captured = self._fake_module(lambda o, u: None)
        self._patch_tools(monkeypatch, fake)
        ctx = _FakeCtx(tmp_path)
        cookies = {"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "d", "extra": "x"}

        with pytest.raises(DownloadError):
            download_video(ctx, "https://bilibili.com/video/BV1",
                           SourceType.BILIBILI, cookies)

        assert captured[0]["cookies"] == {"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "d"}

    def test_bilibili_partial_cookie_degrades_without_cookie(self, monkeypatch, tmp_path):
        # 部分缺字段 → 不注入 cookie，仅一次免登录尝试，并产出降级提示日志
        fake, captured = self._fake_module(lambda o, u: None)
        self._patch_tools(monkeypatch, fake)
        ctx = _FakeCtx(tmp_path)

        with pytest.raises(DownloadError):
            download_video(ctx, "https://bilibili.com/video/BV1",
                           SourceType.BILIBILI, {"SESSDATA": "s"})

        assert len(captured) == 1, "部分 cookie 不应再触发额外降级重试"
        assert "cookies" not in captured[0]
        assert any("降级" in line for _, line in ctx.logs), "应产出免登录降级提示"

    def test_bilibili_login_failure_degrades_to_no_cookie(self, monkeypatch, tmp_path):
        # 完整 cookie 但下载疑似登录失败 → 自动降级免登录重试一次
        def behavior(opts, urls):
            if "cookies" in opts:  # 登录态那次
                raise Exception("login required by platform")

        fake, captured = self._fake_module(behavior)
        self._patch_tools(monkeypatch, fake)
        ctx = _FakeCtx(tmp_path)
        cookies = {"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "d"}

        with pytest.raises(DownloadError):
            download_video(ctx, "https://bilibili.com/video/BV1",
                           SourceType.BILIBILI, cookies)

        assert len(captured) == 2, "登录态失败应再免登录降级一次"
        assert "cookies" in captured[0]
        assert "cookies" not in captured[1]
        assert any("失效" in line or "降级" in line for _, line in ctx.logs)

    def test_local_source_rejected(self, monkeypatch, tmp_path):
        # 调用方应跳过本地来源；误调时防御性拒绝
        fake, _ = self._fake_module(lambda o, u: None)
        self._patch_tools(monkeypatch, fake)
        ctx = _FakeCtx(tmp_path)
        with pytest.raises(DownloadError):
            download_video(ctx, "x", SourceType.LOCAL_VIDEO, None)


# --------------------------------------------------------------------------- #
# 取消信号
# --------------------------------------------------------------------------- #
class TestCancel:
    def test_progress_hook_raises_on_cancel(self, tmp_path):
        class _Ctx:
            cancel = types.SimpleNamespace(is_cancelled=lambda: True)

            def emit_progress(self, *a, **k):
                pass

            def emit_log(self, *a, **k):
                pass

        hook = dl._make_progress_hook(_Ctx())
        with pytest.raises(IngestCancelled):
            hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})

    def test_extract_audio_raises_on_cancel(self, tmp_path):
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg 未安装")

        class _Cancel:
            def is_cancelled(self):
                return True

        ctx = _FakeCtx(tmp_path)
        ctx.cancel = _Cancel()
        # 即使视频存在，进入函数即应因取消抛 IngestCancelled
        with pytest.raises(IngestCancelled):
            extract_audio(ctx, "videos/whatever.mp4")


# --------------------------------------------------------------------------- #
# 工具缺失归类
# --------------------------------------------------------------------------- #
class TestToolMissing:
    def test_download_missing_yt_dlp(self, monkeypatch, tmp_path):
        def _no_yt():
            raise DownloadError(DOWNLOAD_ERR_TOOL_MISSING, "未找到 yt-dlp")

        monkeypatch.setattr(dl, "_require_yt_dlp", _no_yt)
        ctx = _FakeCtx(tmp_path)
        with pytest.raises(DownloadError) as ei:
            download_video(ctx, "https://example.com/x.mp4", SourceType.DIRECT, None)
        assert ei.value.kind == DOWNLOAD_ERR_TOOL_MISSING

    def test_download_missing_ffmpeg(self, monkeypatch, tmp_path):
        fake, _ = TestDownloadCookiePolicy()._fake_module(lambda o, u: None)
        monkeypatch.setattr(dl, "_require_yt_dlp", lambda: fake)

        def _no_ff():
            raise DownloadError(DOWNLOAD_ERR_TOOL_MISSING, "未找到 ffmpeg")

        monkeypatch.setattr(dl, "_require_ffmpeg", _no_ff)
        ctx = _FakeCtx(tmp_path)
        with pytest.raises(DownloadError) as ei:
            download_video(ctx, "https://example.com/x.mp4", SourceType.DIRECT, None)
        assert ei.value.kind == DOWNLOAD_ERR_TOOL_MISSING

    def test_extract_missing_ffmpeg(self, monkeypatch, tmp_path):
        monkeypatch.setattr(aud.shutil, "which", lambda name: None)
        ctx = _FakeCtx(tmp_path)
        with pytest.raises(ExtractError, match="ffmpeg"):
            extract_audio(ctx, "videos/x.mp4")


# --------------------------------------------------------------------------- #
# ffmpeg 提取（真实 ffmpeg，无网络）
# --------------------------------------------------------------------------- #
def _gen_video(path: Path, with_audio: bool, seconds: int = 2):
    """用 ffmpeg 生成测试视频（含/不含静音音轨）。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg 未安装")
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=1",
           "-t", str(seconds)]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-shortest"]
    cmd += ["-f", "mp4", str(path)]
    subprocess.run(cmd, capture_output=True, check=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 未安装")
class TestExtractAudio:
    def test_extracts_16k_mono_wav_and_registers(self, tmp_path):
        ctx = _FakeCtx(tmp_path)
        # 把测试视频放到 ctx 的 video 产物路径
        vid_rel = "videos/task_t1/task_t1.mp4"
        vid_abs = tmp_path / vid_rel
        _gen_video(vid_abs, with_audio=True)

        rel = extract_audio(ctx, vid_rel)

        assert rel == "audio/task_t1/task_t1.wav"
        wav_abs = tmp_path / rel
        assert wav_abs.exists() and wav_abs.stat().st_size > 0
        assert ("audio", rel, wav_abs.stat().st_size) in ctx.products
        # 校验 16kHz 单声道
        fp = shutil.which("ffprobe")
        probe = subprocess.run(
            [fp, "-v", "error", "-show_entries", "stream=sample_rate,channels",
             "-of", "default=noprint_wrappers=1", str(wav_abs)],
            capture_output=True, text=True,
        )
        assert "sample_rate=16000" in probe.stdout
        assert "channels=1" in probe.stdout

    def test_no_audio_track_raises_and_leaves_no_artifact(self, tmp_path):
        ctx = _FakeCtx(tmp_path)
        vid_rel = "videos/task_t1/task_t1.mp4"
        _gen_video(tmp_path / vid_rel, with_audio=False)

        with pytest.raises(ExtractError) as ei:
            extract_audio(ctx, vid_rel)
        assert "音轨" in ei.value.message or "退出码" in ei.value.message
        # 不留半成品
        assert not (tmp_path / "audio" / "task_t1" / "task_t1.wav").exists()

    def test_missing_video_raises(self, tmp_path):
        ctx = _FakeCtx(tmp_path)
        with pytest.raises(ExtractError, match="不存在"):
            extract_audio(ctx, "videos/task_t1/missing.mp4")
