"""结构化日志"""
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def _today_file() -> Path:
    return LOG_DIR / f"vid2note-{datetime.now().strftime('%Y-%m-%d')}.log"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        for key in ("task_id", "provider", "model", "node", "extra"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        extra = ""
        if hasattr(record, "task_id"):
            extra += f" [{record.task_id}]"
        return f"[{ts}] [{record.levelname}]{extra} {record.getMessage()}"


_logger_cache: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    if name in _logger_cache:
        return _logger_cache[name]
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        # 文件 handler（JSON）
        fh = logging.FileHandler(_today_file(), encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        logger.addHandler(fh)
        # 控制台 handler（文本）
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(TextFormatter())
        logger.addHandler(ch)
    _logger_cache[name] = logger
    return logger


class TaskLogger:
    """任务级 logger，自动附加 task_id"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._logger = get_logger("task")

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = {"task_id": self.task_id, "extra": kwargs}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)
