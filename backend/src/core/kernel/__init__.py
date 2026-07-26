"""
vid2note 内核门面(Kernel Facade)
=================================
v1 所有新增模块(media_ingest / speech_to_text / screenshot / pdf_reference /
pipeline.dag / retention / SSE 层等)**必须**从 `core.kernel` 导入内核能力,
不得直接 import 内核各包内部 —— 以保证内核边界稳定,并便于日后从上游 ai_srt2md
cherry-pick 内核修复(LLM 适配 / prompt / SimpleProcessor 等)。

内核范围(对应 design D6「原样复用」类):
- LLM 适配(8 家,LLMFactory 创建)
- prompt 库(prompts/)
- SimpleProcessor(字幕→笔记 + 思维导图)
- 语义对齐 / 内容过滤 / Markdown 生成(aligner / filter / generator)
- SRT 解析 / PDF 解析(parsers/)
- SQLite 持久化(db/)
- 安全防护(utils.security + core.security_constants)+ SRT 校验(utils.srt_validator)
- 日志(utils.logger)
"""
# 字幕→笔记 + 思维导图(原样复用基底)
from ..simple_processor import SimpleProcessor

# 语义对齐 / 内容过滤 / Markdown 生成
from ..aligner import SemanticAligner, AlignedSegment
from ..filter import ContentFilter, FilterResult
from ..generator import MarkdownGenerator, MarkdownOutput

# 任务队列与 worker(v1 在其上加 DAG 编排与并发配置,但不改其并发原语)
from ..task_queue import TaskQueue, get_task_queue
from ..worker import TaskWorker, get_task_worker, start_worker, stop_worker

# LLM 适配(8 家,OpenAI 兼容)
from ...llm import BaseLLM, LLMFactory

# 输入解析(SRT / PDF)
from ...parsers import SRTParser, SubtitleItem, PDFParser, PDFPage, Chapter

# SQLite 持久化
from ...db import Database, TaskRepository

# 日志
from ...utils import logger, TaskLogger

__all__ = [
    # 笔记 + 导图
    "SimpleProcessor",
    # 对齐 / 过滤 / 生成
    "SemanticAligner", "AlignedSegment", "ContentFilter", "FilterResult",
    "MarkdownGenerator", "MarkdownOutput",
    # 队列 / worker
    "TaskQueue", "get_task_queue",
    "TaskWorker", "get_task_worker", "start_worker", "stop_worker",
    # LLM
    "BaseLLM", "LLMFactory",
    # 解析
    "SRTParser", "SubtitleItem", "PDFParser", "PDFPage", "Chapter",
    # 持久化
    "Database", "TaskRepository",
    # 日志
    "logger", "TaskLogger",
]
