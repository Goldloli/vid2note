"""内核门面冒烟测试(task 1.2)。
验证 core.kernel 统一入口能聚合 v1 新模块所需的全部关键内核能力;
v1 新模块(media_ingest / speech_to_text / screenshot / pdf_reference / dag / retention / SSE)
必须从 core.kernel 取内核,不穿透内部。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.kernel import (
    SimpleProcessor,
    SemanticAligner, AlignedSegment, ContentFilter, FilterResult,
    MarkdownGenerator, MarkdownOutput,
    TaskQueue, get_task_queue,
    TaskWorker, get_task_worker, start_worker, stop_worker,
    BaseLLM, LLMFactory,
    SRTParser, SubtitleItem, PDFParser, PDFPage, Chapter,
    Database, TaskRepository,
    logger, TaskLogger,
)


def test_facade_symbols_are_types():
    """门面聚合的内核符号都可导入且为预期类型(类/可调用)"""
    for cls in (SimpleProcessor, SemanticAligner, ContentFilter, MarkdownGenerator,
                TaskQueue, TaskWorker, BaseLLM, LLMFactory,
                SRTParser, PDFParser, Database, TaskRepository, TaskLogger):
        assert isinstance(cls, type), f"{cls!r} 不是类"
    assert callable(get_task_queue) and callable(start_worker)


def test_facade_all_covers_v1_entry_points():
    """门面 __all__ 声明并真正导出了 v1 新模块需要的主要内核入口"""
    from src.core import kernel as k
    must_have = ["SimpleProcessor", "LLMFactory", "TaskQueue",
                 "SRTParser", "TaskRepository", "logger", "TaskLogger"]
    for name in must_have:
        assert name in k.__all__, f"门面 __all__ 缺少 {name}"
        assert hasattr(k, name), f"门面未导出 {name}"
