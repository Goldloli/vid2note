"""统一错误体系"""
from typing import Optional


class Vid2NoteError(Exception):
    """基类"""
    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN",
        retryable: bool = False,
        user_message: Optional[str] = None,
        step: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.user_message = user_message or message
        self.step = step

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "user_message": self.user_message,
            "step": self.step,
        }


# ── Download ───────────────────────────────
class DownloadError(Vid2NoteError): ...

class DownloadURLInvalid(DownloadError):
    def __init__(self, url: str):
        super().__init__(
            f"URL 格式不正确: {url}",
            code="DOWNLOAD_URL_INVALID",
            retryable=False,
            user_message="URL 格式不正确，请检查输入",
            step="download",
        )

class DownloadNetworkError(DownloadError):
    def __init__(self, url: str, detail: str = ""):
        super().__init__(
            f"网络错误: {url} {detail}",
            code="DOWNLOAD_NETWORK_ERROR",
            retryable=True,
            user_message="网络连接失败，请检查网络后重试",
            step="download",
        )

class DownloadVideoNotFound(DownloadError):
    def __init__(self, url: str):
        super().__init__(
            f"视频不存在: {url}",
            code="DOWNLOAD_VIDEO_NOT_FOUND",
            retryable=False,
            user_message="视频不存在或已被删除",
            step="download",
        )

class DownloadGeoBlocked(DownloadError):
    def __init__(self, url: str):
        super().__init__(
            f"地区限制: {url}",
            code="DOWNLOAD_GEO_BLOCKED",
            retryable=True,
            user_message="该视频在当前地区不可用，请尝试使用代理",
            step="download",
        )

class DownloadCookieExpired(DownloadError):
    def __init__(self):
        super().__init__(
            "Cookie 已过期",
            code="DOWNLOAD_COOKIE_EXPIRED",
            retryable=False,
            user_message="Cookie 已过期，请到设置页更新",
            step="download",
        )

class DownloadRateLimited(DownloadError):
    def __init__(self, url: str):
        super().__init__(
            f"被限流: {url}",
            code="DOWNLOAD_RATE_LIMITED",
            retryable=True,
            user_message="下载被限制，请等待后重试",
            step="download",
        )

class DownloadBinaryMissing(DownloadError):
    def __init__(self, name: str):
        super().__init__(
            f"二进制缺失: {name}",
            code="DOWNLOAD_BINARY_MISSING",
            retryable=False,
            user_message=f"未找到 {name}，请检查安装",
            step="download",
        )

class DownloadDiskFull(DownloadError):
    def __init__(self):
        super().__init__(
            "磁盘空间不足",
            code="DOWNLOAD_DISK_FULL",
            retryable=False,
            user_message="磁盘空间不足，请清理后重试",
            step="download",
        )

# ── ASR ────────────────────────────────────
class ASRError(Vid2NoteError): ...

class ASRToolBChanged(ASRError):
    def __init__(self, detail: str = ""):
        super().__init__(
            f"AsrTools b 接口结构变更: {detail}",
            code="ASRTOOL_B_CHANGED",
            retryable=False,
            user_message="语音识别接口有变化，请等待更新或切换其他提供商",
            step="transcribe",
        )

class ASRNetworkError(ASRError):
    def __init__(self, detail: str = ""):
        super().__init__(
            f"ASR 网络错误: {detail}",
            code="ASR_NETWORK_ERROR",
            retryable=True,
            user_message="语音识别服务连接失败，请检查网络后重试",
            step="transcribe",
        )

class ASRModelNotFound(ASRError):
    def __init__(self, model_id: str):
        super().__init__(
            f"模型未下载: {model_id}",
            code="ASR_MODEL_NOT_FOUND",
            retryable=False,
            user_message=f"模型 {model_id} 未下载，请到设置页下载",
            step="transcribe",
        )

class ASRDeviceUnavailable(ASRError):
    def __init__(self, device: str):
        super().__init__(
            f"设备不可用: {device}",
            code="ASR_DEVICE_UNAVAILABLE",
            retryable=False,
            user_message=f"计算设备 {device} 不可用，请检查配置",
            step="transcribe",
        )

# ── LLM ────────────────────────────────────
class LLMError(Vid2NoteError): ...

class LLMRateLimited(LLMError):
    def __init__(self, provider: str):
        super().__init__(
            f"{provider} 被限流",
            code="LLM_RATE_LIMITED",
            retryable=True,
            user_message="AI 服务被限制，请等待后重试",
            step="organize",
        )

class LLMAPIError(LLMError):
    def __init__(self, provider: str, detail: str = ""):
        super().__init__(
            f"{provider} API 错误: {detail}",
            code="LLM_API_ERROR",
            retryable=True,
            user_message="AI 服务调用失败，请检查配置后重试",
            step="organize",
        )

class LLMTimeout(LLMError):
    def __init__(self, provider: str):
        super().__init__(
            f"{provider} 超时",
            code="LLM_TIMEOUT",
            retryable=True,
            user_message="AI 服务响应超时，请稍后重试",
            step="organize",
        )

class LLMInvalidOutput(LLMError):
    def __init__(self, detail: str = ""):
        super().__init__(
            f"LLM 输出格式异常: {detail}",
            code="LLM_INVALID_OUTPUT",
            retryable=True,
            user_message="AI 返回内容格式异常，请重试",
            step="organize",
        )

# ── Pipeline ───────────────────────────────
class PipelineError(Vid2NoteError): ...

class PipelineUpstreamMissing(PipelineError):
    def __init__(self, node: str, missing: list[str]):
        super().__init__(
            f"节点 {node} 缺少上游产物: {missing}",
            code="PIPELINE_UPSTREAM_MISSING",
            retryable=False,
            user_message="前置步骤未完成，请等待或重试",
            step=node,
        )

class PipelineCircularDependency(PipelineError):
    def __init__(self):
        super().__init__(
            "Pipeline 存在循环依赖",
            code="PIPELINE_CIRCULAR",
            retryable=False,
            user_message="任务配置异常，请联系开发者",
            step="pipeline",
        )
