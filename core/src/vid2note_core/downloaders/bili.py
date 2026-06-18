"""纯 Python Bilibili 下载器（基于官方 web API）。

不依赖任何外部下载二进制（BBDown/aria2c）。流程：
  1. 获取 buvid（匿名设备指纹，反爬必需）
  2. bvid → aid/cid（x/web-interface/view API）
  3. wbi 签名 + playurl 请求 → DASH 流地址（视频+音频分离）
  4. httpx 流式下载视频流 + 音频流
  5. ffmpeg 混流为 mp4

支持匿名 720P 和登录态 1080P+（通过 cookie 文件提供 SESSDATA）。

参考实现：BiliTools（github.com/jeasonstudio/BiliTools），wbi 签名算法来自
bilibili-API-collect（SocialSisterYi）。
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from vid2note_core.audio.ffmpeg_binary import get_ffmpeg
from vid2note_core.downloaders.base import DownloadOpts, DownloadResult, IDownloader
from vid2note_core.errors import DownloadError

logger = logging.getLogger(__name__)

# bilibili 强制要求的浏览器 headers（缺 Referer 会 403）
_BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}

# wbi 签名打乱表（64 元素，从 BiliTools auth.ts 原样移植）
_MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

# wbi 签名时要从值中剔除的字符（bilibili 的特殊过滤规则）
_WBI_CHR_FILTER = re.compile(r"[!'()*]")

_DOWNLOAD_TIMEOUT = 1800  # 30 分钟上限
_API_TIMEOUT = httpx.Timeout(connect=10, read=60, write=10, pool=10)


def _extract_bvid(url: str) -> str:
    """从 URL 提取 BV 号。支持 /video/BVxxx、b23.tv 短链（需跳转解析）。"""
    m = re.search(r"(BV[a-zA-Z0-9]{10})", url)
    if m:
        return m.group(1)
    raise DownloadError(
        f"无法从 URL 提取 BV 号: {url}",
        code="DOWNLOAD_INVALID_URL",
        retryable=False,
        user_message="无法识别的 bilibili 链接，请确认是有效的视频地址",
        step="download",
    )


def _get_buvid(client: httpx.Client) -> dict[str, str]:
    """获取 buvid3/buvid4（匿名设备指纹，反爬必需）。

    流程：GET bilibili 首页（拿 Set-Cookie buvid3）→ GET finger/spi（拿 b_3/b_4）。
    """
    cookies: dict[str, str] = {}
    # 1. GET 首页，从 Set-Cookie 读 buvid3
    resp = client.get("https://www.bilibili.com", headers=_BILI_HEADERS)
    for cookie in resp.headers.get_list("set-cookie"):
        m = re.match(r"(buvid3)=([^;]+)", cookie)
        if m:
            cookies[m.group(1)] = m.group(2)

    # 2. GET finger/spi 拿 b_3/b_4
    resp = client.get("https://api.bilibili.com/x/frontend/finger/spi", headers=_BILI_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise DownloadError(
            f"获取 buvid 失败: {data.get('message', 'unknown')}",
            code="DOWNLOAD_BUVID_FAILED",
            retryable=True,
            step="download",
        )
    spi = data["data"]
    cookies.setdefault("buvid3", spi["b_3"])
    cookies["buvid4"] = spi["b_4"]
    return cookies


def _resolve_bvid(client: httpx.Client, bvid: str) -> tuple[int, int, str]:
    """bvid → (aid, cid, title)。调用 x/web-interface/view API。"""
    resp = client.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        headers=_BILI_HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise DownloadError(
            f"解析视频信息失败: {data.get('message', 'unknown')} (bvid={bvid})",
            code="DOWNLOAD_VIDEO_INFO_FAILED",
            retryable=False,
            user_message="视频不存在或已被删除",
            step="download",
        )
    d = data["data"]
    return int(d["aid"]), int(d["cid"]), str(d.get("title", bvid))


def _wbi_sign(client: httpx.Client, params: dict[str, str | int]) -> str:
    """对请求参数做 wbi 签名，返回完整的 query string（含 w_rid）。

    算法：从 nav API 拿 img_key+sub_key → 打乱表拼接 mixin_key →
    参数排序+过滤+url-encode → md5(query + mixin_key) = w_rid。
    """
    # 1. GET nav 拿 wbi_img 的 img_url/sub_url
    resp = client.get("https://api.bilibili.com/x/web-interface/nav", headers=_BILI_HEADERS)
    resp.raise_for_status()
    nav = resp.json()["data"]["wbi_img"]
    img_key = nav["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub_key = nav["sub_url"].rsplit("/", 1)[-1].split(".")[0]

    # 2. 打乱表拼接 mixin_key（取前 32 字符）
    raw = img_key + sub_key
    mixin_key = "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB)[:32]

    # 3. 加标准参数
    params = dict(params)
    params["wts"] = str(int(time.time()))
    params["dm_img_str"] = "bm8gd2ViZ"
    params["dm_cover_img_str"] = "bm8gd2ViZ2wgZXh0ZW5zaW"
    params["dm_img_list"] = "[]"

    # 4. 排序 + 过滤 + url-encode
    query = "&".join(
        f"{quote(k, safe='')}={quote(_WBI_CHR_FILTER.sub('', str(v)), safe='')}"
        for k, v in sorted(params.items())
    )

    # 5. md5 签名
    w_rid = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return f"{query}&w_rid={w_rid}"


def _get_playurl(client: httpx.Client, aid: int, cid: int, sessdata: str) -> dict[str, str]:
    """请求 playurl（wbi 签名），解析 DASH 流，返回 {video_url, audio_url, quality}。

    有 SESSDATA → qn=127 fnval=4048（最高画质）；无 → qn=64 fnval=16（720P DASH）。
    """
    if sessdata:
        params: dict[str, str | int] = {
            "avid": aid,
            "cid": cid,
            "qn": 127,
            "fnver": 0,
            "fnval": 4048,  # DASH + 4K + HDR + 杜比 + AV1
            "fourk": 1,
        }
    else:
        params = {
            "avid": aid,
            "cid": cid,
            "qn": 64,  # 720P
            "fnver": 0,
            "fnval": 16,  # 基础 DASH
            "fourk": 1,
        }

    signed_query = _wbi_sign(client, params)
    resp = client.get(
        f"https://api.bilibili.com/x/player/wbi/playurl?{signed_query}",
        headers=_BILI_HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise DownloadError(
            f"获取播放地址失败: {data.get('message', 'unknown')}",
            code="DOWNLOAD_PLAYURL_FAILED",
            retryable=True,
            step="download",
        )

    dash = data["data"]["dash"]
    if not dash.get("video") or not dash.get("audio"):
        raise DownloadError(
            "playurl 未返回 DASH 流（可能需要登录或视频不支持 DASH）",
            code="DOWNLOAD_NO_DASH",
            retryable=True,
            user_message="无法获取视频流，可能需要登录或更换视频",
            step="download",
        )

    # 视频流：优先 H.264（codecid=7，兼容性最好），同 codec 选最高画质
    videos = dash["video"]
    h264 = [v for v in videos if v.get("codecid", 7) == 7]
    pool = h264 if h264 else videos
    video = max(pool, key=lambda v: v.get("id", 0))

    # 音频流：选最高码率（bandwidth 最大）
    audios = dash["audio"]
    audio = max(audios, key=lambda a: a.get("bandwidth", 0))

    quality_map = {
        16: "360P",
        32: "480P",
        64: "720P",
        80: "1080P",
        112: "1080P+",
        116: "1080P60",
        120: "4K",
        127: "8K",
    }

    return {
        "video_url": video["baseUrl"],
        "audio_url": audio["baseUrl"],
        "quality": quality_map.get(video.get("id", 0), f"qn{video.get('id')}"),
    }


def _parse_cookie(opts: DownloadOpts) -> str:
    """从 opts.cookie_path 解析 SESSDATA，无则返回空串（匿名下载）。"""
    if not opts.cookie_path:
        return ""
    path = Path(opts.cookie_path)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    # 支持 Netscape cookie 格式和 "SESSDATA=xxx" 纯文本格式
    m = re.search(r"SESSDATA\s*[=\t]\s*([^\s;]+)", text)
    return m.group(1) if m else ""


def _download_stream(client: httpx.Client, url: str, dest: Path) -> None:
    """httpx 流式下载单个 DASH 流到文件。"""
    with client.stream("GET", url, headers=_BILI_HEADERS, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)


def _merge_streams(video_path: Path, audio_path: Path, output: Path) -> None:
    """ffmpeg 混流视频+音频 DASH 流为 mp4（-c copy 不重编码）。"""
    cmd = [
        str(get_ffmpeg()),
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "warning",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
        "-y",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired as e:
        raise DownloadError(
            "ffmpeg 混流超时",
            code="DOWNLOAD_MUX_TIMEOUT",
            retryable=True,
            step="download",
        ) from e
    if result.returncode != 0:
        raise DownloadError(
            f"ffmpeg 混流失败: {result.stderr[:500]}",
            code="DOWNLOAD_MUX_FAILED",
            retryable=False,
            step="download",
        )


class BiliDownloader(IDownloader):
    """纯 Python Bilibili 下载器（wbi 签名 + DASH 流 + ffmpeg 混流）。

    无需 BBDown 或 aria2c。匿名模式下最高 720P；提供 SESSDATA cookie 后
    可下载 1080P/4K。
    """

    name = "bili"

    def can_handle(self, url_or_path: str) -> bool:
        return "bilibili.com" in url_or_path or "b23.tv" in url_or_path

    def download(self, url: str, dest_dir: Path, opts: DownloadOpts) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        bvid = _extract_bvid(url)
        sessdata = _parse_cookie(opts)
        proxy = opts.proxy

        logger.info(
            "[BiliDownloader] 开始下载 %s（SESSDATA: %s）", bvid, "有" if sessdata else "无"
        )

        try:
            with httpx.Client(
                timeout=_API_TIMEOUT,
                proxy=proxy,
                follow_redirects=True,
            ) as client:
                # 如果有 cookie 文件，设置到 client
                if sessdata:
                    client.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")

                # 1. 获取 buvid
                buvid_cookies = _get_buvid(client)
                for k, v in buvid_cookies.items():
                    client.cookies.set(k, v, domain=".bilibili.com")

                # 2. bvid → aid/cid/title
                aid, cid, title = _resolve_bvid(client, bvid)
                logger.info(
                    "[BiliDownloader] %s → aid=%s cid=%s title=%s", bvid, aid, cid, title[:40]
                )

                # 3. playurl → DASH 流
                streams = _get_playurl(client, aid, cid, sessdata)
                logger.info("[BiliDownloader] 画质: %s", streams["quality"])

                # 4. 下载视频流 + 音频流（DASH 分离）
                video_tmp = dest_dir / f"{bvid}_video.m4s"
                audio_tmp = dest_dir / f"{bvid}_audio.m4s"
                logger.info("[BiliDownloader] 下载视频流...")
                _download_stream(client, streams["video_url"], video_tmp)
                logger.info("[BiliDownloader] 下载音频流...")
                _download_stream(client, streams["audio_url"], audio_tmp)

        except DownloadError:
            raise
        except httpx.HTTPError as e:
            raise DownloadError(
                f"网络请求失败: {e}",
                code="DOWNLOAD_NETWORK_ERROR",
                retryable=True,
                user_message="网络连接失败，请检查网络后重试",
                step="download",
            ) from e
        except Exception as e:
            raise DownloadError(
                f"下载失败: {e}",
                code="DOWNLOAD_FAILED",
                retryable=False,
                user_message="视频下载失败，请检查链接是否有效",
                step="download",
            ) from e

        # 5. ffmpeg 混流
        output = dest_dir / f"{bvid}.mp4"
        logger.info("[BiliDownloader] 混流为 mp4...")
        _merge_streams(video_tmp, audio_tmp, output)

        # 清理临时文件
        video_tmp.unlink(missing_ok=True)
        audio_tmp.unlink(missing_ok=True)

        logger.info(
            "[BiliDownloader] 完成: %s (%.1f MB)", output.name, output.stat().st_size / 1048576
        )
        return DownloadResult(
            video_path=output,
            metadata={"title": title, "bvid": bvid, "quality": streams["quality"]},
        )
