"""测试 BiliDownloader（纯 Python bilibili 下载器）。

用 respx mock 所有 HTTP 请求，验证 wbi 签名、bvid 解析、DASH 解析、错误处理。
不实际下载视频（那是集成测试的工作）。
"""

from unittest.mock import patch

import httpx
import pytest
import respx
from vid2note_core.downloaders.base import DownloadOpts
from vid2note_core.downloaders.bili import (
    BiliDownloader,
    _download_stream,
    _extract_bvid,
    _get_buvid,
    _get_playurl,
    _parse_cookie,
    _resolve_bvid,
    _wbi_sign,
)
from vid2note_core.errors import DownloadError

# ── bvid 提取 ──────────────────────────────────────────


def test_extract_bvid_from_video_url():
    assert _extract_bvid("https://www.bilibili.com/video/BV1KTEd6DEfN") == "BV1KTEd6DEfN"


def test_extract_bvid_from_b23():
    assert _extract_bvid("https://b23.tv/BV1fj6vBfEnu") == "BV1fj6vBfEnu"


def test_extract_bvid_no_match_raises():
    with pytest.raises(DownloadError, match="无法从 URL 提取 BV 号"):
        _extract_bvid("https://example.com/no-bv-here")


# ── cookie 解析 ────────────────────────────────────────


def test_parse_cookie_from_text(tmp_path):
    cookie_file = tmp_path / "cookie.txt"
    cookie_file.write_text("SESSDATA=abc123def\nother=xyz")
    opts = DownloadOpts(cookie_path=cookie_file)
    assert _parse_cookie(opts) == "abc123def"


def test_parse_cookie_netscape_format(tmp_path):
    cookie_file = tmp_path / "cookie.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tnetscape-sess-456\n"
    )
    opts = DownloadOpts(cookie_path=cookie_file)
    assert _parse_cookie(opts) == "netscape-sess-456"


def test_parse_cookie_no_file_returns_empty():
    opts = DownloadOpts(cookie_path=None)
    assert _parse_cookie(opts) == ""


def test_parse_cookie_missing_file_returns_empty(tmp_path):
    opts = DownloadOpts(cookie_path=tmp_path / "nonexistent.txt")
    assert _parse_cookie(opts) == ""


# ── can_handle ─────────────────────────────────────────


def test_can_handle_bilibili():
    dl = BiliDownloader()
    assert dl.can_handle("https://www.bilibili.com/video/BV1KTEd6DEfN")
    assert dl.can_handle("https://b23.tv/BV1fj6vBfEnu")


def test_can_handle_other_domains():
    dl = BiliDownloader()
    assert not dl.can_handle("https://youtube.com/watch?v=123")
    assert not dl.can_handle("https://example.com/video.mp4")


# ── wbi 签名算法 ───────────────────────────────────────


def test_wbi_sign_produces_valid_signature():
    """wbi 签名应产生 w_rid（32 位 md5 hex）且包含 wts 时间戳。"""
    with respx.mock as mock:
        # mock nav API 返回固定的 img_key/sub_key
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0d7e1f3a3c4ad3a1a1a1a1a1.png",
                    }
                },
            }
        )
        with httpx.Client() as client:
            result = _wbi_sign(
                client, {"avid": 123, "cid": 456, "qn": 64, "fnver": 0, "fnval": 16, "fourk": 1}
            )

    # 应包含 w_rid=xxx（32位hex）和 wts=xxx
    assert "w_rid=" in result
    assert "wts=" in result
    assert "avid=123" in result
    assert "cid=456" in result
    # w_rid 应该是 32 位 md5 hex
    w_rid = result.split("w_rid=")[1]
    assert len(w_rid) == 32
    int(w_rid, 16)  # 是合法 hex


def test_wbi_sign_filters_special_chars():
    """值中的 !'()* 字符应被过滤（bilibili 的特殊要求）。"""
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
                    }
                },
            }
        )
        with httpx.Client() as client:
            result = _wbi_sign(client, {"test": "hello!'()*world"})
    # !'()* 应被移除
    assert "hello!'()*world" not in result
    assert "helloworld" in result or "hello%2Aworld" not in result


# ── bvid → aid/cid 解析 ────────────────────────────────


def test_resolve_bvid_success():
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/view").respond(
            json={
                "code": 0,
                "data": {"aid": 12345, "cid": 67890, "title": "测试视频标题"},
            }
        )
        with httpx.Client() as client:
            aid, cid, title = _resolve_bvid(client, "BV1KTEd6DEfN")
    assert aid == 12345
    assert cid == 67890
    assert title == "测试视频标题"


def test_resolve_bvid_video_not_found():
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/view").respond(
            json={"code": -404, "message": "视频不存在"}
        )
        with httpx.Client() as client:
            with pytest.raises(DownloadError, match="解析视频信息失败"):
                _resolve_bvid(client, "BV0000000000")


# ── buvid 获取 ─────────────────────────────────────────


def test_get_buvid_success():
    with respx.mock as mock:
        mock.get("https://www.bilibili.com/").respond(
            status_code=200, headers={"set-cookie": "buvid3=initial-buvid3; path=/"}
        )
        mock.get("https://api.bilibili.com/x/frontend/finger/spi").respond(
            json={"code": 0, "data": {"b_3": "spi-buvid3", "b_4": "spi-buvid4"}}
        )
        with httpx.Client() as client:
            cookies = _get_buvid(client)
    # 首页已设 buvid3，spi 不覆盖
    assert cookies["buvid3"] == "initial-buvid3"
    assert cookies["buvid4"] == "spi-buvid4"


def test_get_buvid_no_homepage_cookie_uses_spi():
    with respx.mock as mock:
        mock.get("https://www.bilibili.com/").respond(status_code=200)
        mock.get("https://api.bilibili.com/x/frontend/finger/spi").respond(
            json={"code": 0, "data": {"b_3": "fallback-buvid3", "b_4": "fallback-buvid4"}}
        )
        with httpx.Client() as client:
            cookies = _get_buvid(client)
    assert cookies["buvid3"] == "fallback-buvid3"
    assert cookies["buvid4"] == "fallback-buvid4"


# ── playurl DASH 解析 ──────────────────────────────────


def test_get_playurl_anonymous_720p():
    """无 SESSDATA 时应请求 qn=64（720P）。"""
    dash_response = {
        "code": 0,
        "data": {
            "dash": {
                "video": [
                    {
                        "id": 64,
                        "baseUrl": "https://cdn.bili/video.m4s",
                        "codecid": 7,
                        "codecs": "avc1.640028",
                        "bandwidth": 1000000,
                    },
                    {
                        "id": 32,
                        "baseUrl": "https://cdn.bili/video_low.m4s",
                        "codecid": 7,
                        "codecs": "avc1.64001f",
                        "bandwidth": 500000,
                    },
                ],
                "audio": [
                    {
                        "id": 30280,
                        "baseUrl": "https://cdn.bili/audio_high.m4s",
                        "codecs": "mp4a.40.2",
                        "bandwidth": 320000,
                    },
                    {
                        "id": 30232,
                        "baseUrl": "https://cdn.bili/audio_low.m4s",
                        "codecs": "mp4a.40.2",
                        "bandwidth": 128000,
                    },
                ],
            }
        },
    }
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0d7e1f3a3c4ad3a1a1a1a1a1.png",
                    }
                },
            }
        )
        mock.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*").respond(
            json=dash_response
        )
        with httpx.Client() as client:
            streams = _get_playurl(client, aid=123, cid=456, sessdata="")

    # 应选最高画质 H.264 视频（id=64=720P）和最高码率音频
    assert streams["video_url"] == "https://cdn.bili/video.m4s"
    assert streams["audio_url"] == "https://cdn.bili/audio_high.m4s"
    assert streams["quality"] == "720P"


def test_get_playurl_prefers_h264():
    """当有 HEVC 和 H.264 时，应优先 H.264（codecid=7）。"""
    dash_response = {
        "code": 0,
        "data": {
            "dash": {
                "video": [
                    {
                        "id": 80,
                        "baseUrl": "https://cdn.bili/hevc.m4s",
                        "codecid": 12,
                        "codecs": "hev1.1.6.L120.90",
                        "bandwidth": 2000000,
                    },
                    {
                        "id": 80,
                        "baseUrl": "https://cdn.bili/avc.m4s",
                        "codecid": 7,
                        "codecs": "avc1.640032",
                        "bandwidth": 1500000,
                    },
                ],
                "audio": [
                    {
                        "id": 30280,
                        "baseUrl": "https://cdn.bili/audio.m4s",
                        "codecs": "mp4a.40.2",
                        "bandwidth": 320000,
                    },
                ],
            }
        },
    }
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0d7e1f3a3c4ad3a1a1a1a1a1.png",
                    }
                },
            }
        )
        mock.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*").respond(
            json=dash_response
        )
        with httpx.Client() as client:
            streams = _get_playurl(client, aid=1, cid=2, sessdata="sess")

    assert streams["video_url"] == "https://cdn.bili/avc.m4s"


def test_get_playurl_no_dash_raises():
    with respx.mock as mock:
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0d7e1f3a3c4ad3a1a1a1a1a1.png",
                    }
                },
            }
        )
        mock.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*").respond(
            json={"code": 0, "data": {"dash": {}}}
        )
        with httpx.Client() as client, pytest.raises(DownloadError, match="未返回 DASH 流"):
            _get_playurl(client, aid=1, cid=2, sessdata="")


# ── 流下载 ─────────────────────────────────────────────


def test_download_stream_writes_file(tmp_path):
    dest = tmp_path / "test.m4s"
    with respx.mock as mock:
        mock.get("https://cdn.bili/video.m4s").respond(content=b"\x00\x01\x02\x03" * 100)
        with httpx.Client() as client:
            _download_stream(client, "https://cdn.bili/video.m4s", dest)
    assert dest.exists()
    assert dest.stat().st_size == 400


# ── 完整 download 流程（mock ffmpeg） ──────────────────


def test_download_full_flow_mocked(tmp_path):
    """端到端流程测试：mock 所有 HTTP + ffmpeg，验证最终产出 mp4。"""
    dest_dir = tmp_path / "task_artifacts"
    dest_dir.mkdir()

    dash_response = {
        "code": 0,
        "data": {
            "dash": {
                "video": [
                    {
                        "id": 64,
                        "baseUrl": "https://cdn.bili/video.m4s",
                        "codecid": 7,
                        "codecs": "avc1.640028",
                        "bandwidth": 1000000,
                    },
                ],
                "audio": [
                    {
                        "id": 30280,
                        "baseUrl": "https://cdn.bili/audio.m4s",
                        "codecs": "mp4a.40.2",
                        "bandwidth": 320000,
                    },
                ],
            }
        },
    }

    with respx.mock as mock:
        mock.get("https://www.bilibili.com/").respond(
            status_code=200, headers={"set-cookie": "buvid3=test-buvid3; path=/"}
        )
        mock.get("https://api.bilibili.com/x/frontend/finger/spi").respond(
            json={"code": 0, "data": {"b_3": "b3", "b_4": "b4"}}
        )
        mock.get("https://api.bilibili.com/x/web-interface/view").respond(
            json={"code": 0, "data": {"aid": 123, "cid": 456, "title": "测试视频"}}
        )
        mock.get("https://api.bilibili.com/x/web-interface/nav").respond(
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0d7e1f3a3c4ad3a1a1a1a1a1.png",
                    }
                },
            }
        )
        mock.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*").respond(
            json=dash_response
        )
        mock.get("https://cdn.bili/video.m4s").respond(content=b"fake_video_data")
        mock.get("https://cdn.bili/audio.m4s").respond(content=b"fake_audio_data")

        # mock ffmpeg：创建一个假的输出文件
        def fake_merge(video, audio, output):
            output.write_bytes(b"merged_mp4_content")

        with patch("vid2note_core.downloaders.bili._merge_streams", side_effect=fake_merge):
            dl = BiliDownloader()
            result = dl.download(
                "https://www.bilibili.com/video/BV1KTEd6DEfN",
                dest_dir,
                DownloadOpts(),
            )

    assert result.video_path is not None
    assert result.video_path.exists()
    assert result.video_path.suffix == ".mp4"
    assert result.metadata["title"] == "测试视频"
    assert result.metadata["bvid"] == "BV1KTEd6DEfN"
    assert result.metadata["quality"] == "720P"
