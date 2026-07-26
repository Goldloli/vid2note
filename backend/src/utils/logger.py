"""
日志管理模块
统一处理应用日志，保存到文件
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
import json

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 当前日期作为日志文件名
def get_log_file() -> Path:
    """获取当天的日志文件路径"""
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"backend-{today}.log"

class JsonFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    def format(self, record):
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # 添加额外字段
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id
        if hasattr(record, "provider"):
            log_data["provider"] = record.provider
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        # 如果有异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)

class TextFormatter(logging.Formatter):
    """文本格式日志格式化器"""
    def format(self, record):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname
        message = record.getMessage()

        # 构建额外信息
        extras = []
        if hasattr(record, "task_id"):
            extras.append(f"task={record.task_id}")
        if hasattr(record, "provider"):
            extras.append(f"provider={record.provider}")

        extra_str = f" [{', '.join(extras)}]" if extras else ""

        formatted = f"[{timestamp}] [{level}]{extra_str} {message}"

        # 如果有异常信息
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted

def setup_logger(name: str = "app") -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 文件处理器 - 文本格式（便于人类阅读）
    file_handler = logging.FileHandler(get_log_file(), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(TextFormatter())

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(TextFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# 全局日志实例
logger = setup_logger()

# 便捷函数
def debug(msg: str, **kwargs):
    """记录调试日志"""
    extra = {"extra_data": kwargs} if kwargs else {}
    logger.debug(msg, extra=extra)

def info(msg: str, **kwargs):
    """记录信息日志"""
    extra = {"extra_data": kwargs} if kwargs else {}
    logger.info(msg, extra=extra)

def warning(msg: str, **kwargs):
    """记录警告日志"""
    extra = {"extra_data": kwargs} if kwargs else {}
    logger.warning(msg, extra=extra)

def error(msg: str, **kwargs):
    """记录错误日志"""
    extra = {"extra_data": kwargs} if kwargs else {}
    logger.error(msg, extra=extra)

def exception(msg: str, **kwargs):
    """记录异常日志（包含堆栈）"""
    extra = {"extra_data": kwargs} if kwargs else {}
    logger.exception(msg, extra=extra)

def task_log(task_id: str, msg: str, level: str = "info", **kwargs):
    """记录任务相关日志"""
    extra = {"task_id": task_id}
    if kwargs:
        extra["extra_data"] = kwargs

    getattr(logger, level.lower())(msg, extra=extra)

def llm_log(provider: str, msg: str, level: str = "info", **kwargs):
    """记录 LLM 相关日志"""
    extra = {"provider": provider}
    if kwargs:
        extra["extra_data"] = kwargs

    getattr(logger, level.lower())(f"[LLM:{provider}] {msg}", extra=extra)

class TaskLogger:
    """任务日志上下文管理器"""
    def __init__(self, task_id: str):
        self.task_id = task_id

    def debug(self, msg: str, **kwargs):
        task_log(self.task_id, msg, "debug", **kwargs)

    def info(self, msg: str, **kwargs):
        task_log(self.task_id, msg, "info", **kwargs)

    def warning(self, msg: str, **kwargs):
        task_log(self.task_id, msg, "warning", **kwargs)

    def error(self, msg: str, **kwargs):
        task_log(self.task_id, msg, "error", **kwargs)

    def exception(self, msg: str, **kwargs):
        extra = {"task_id": self.task_id, "extra_data": kwargs} if kwargs else {"task_id": self.task_id}
        logger.exception(msg, extra=extra)
