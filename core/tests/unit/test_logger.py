"""测试日志模块"""

import json
import logging

from vid2note_core.utils.logger import JsonFormatter, get_logger


def test_json_formatter():
    fmt = JsonFormatter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
    record.task_id = "task_abc"
    output = fmt.format(record)
    data = json.loads(output)
    assert data["message"] == "hello"
    assert data["task_id"] == "task_abc"
    assert "timestamp" in data


def test_get_logger_returns_logger():
    logger = get_logger("test")
    assert isinstance(logger, logging.Logger)


def test_task_logger():
    from vid2note_core.utils.logger import TaskLogger

    tlog = TaskLogger("task_abc")
    # 不抛异常即可
    tlog.info("test", provider="qwen")
