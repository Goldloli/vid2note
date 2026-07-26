"""
后台任务工作器
负责任务的异步处理和状态更新
"""
import asyncio
from typing import Optional
from pathlib import Path

try:
    from ..models.task import Task, TaskStatus
except ImportError:
    from models.task import Task, TaskStatus
try:
    from .task_queue import TaskQueue, get_task_queue
except ImportError:
    from core.task_queue import TaskQueue, get_task_queue
try:
    from ..utils.logger import TaskLogger, error as log_error, info as log_info
except ImportError:
    from utils.logger import TaskLogger, error as log_error, info as log_info
try:
    from ..utils.security import secure_filename
except ImportError:
    from utils.security import secure_filename


class TaskWorker:
    """后台任务工作器"""

    def __init__(
        self,
        task_queue: Optional[TaskQueue] = None,
        poll_interval: float = 2.0
    ):
        """
        初始化工作器

        Args:
            task_queue: 任务队列
            poll_interval: 轮询间隔(秒)
        """
        self.task_queue = task_queue or get_task_queue()
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        # 使用信号量控制并发，确保原子性的检查-获取操作
        self._processing_semaphore = asyncio.Semaphore(
            self.task_queue.max_concurrent if self.task_queue else 3
        )
        # 活跃任务跟踪（用于资源监控）
        self._active_tasks: set[asyncio.Task] = set()
        self._max_tasks_hard_limit = (self.task_queue.max_concurrent if self.task_queue else 3) * 2
        self._tasks_lock = asyncio.Lock()

    async def start(self):
        """启动工作器"""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._task = asyncio.create_task(self._worker_loop())
            log_info("[TaskWorker] Started")

    async def stop(self):
        """停止工作器"""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            log_info("[TaskWorker] Stopped")

    async def _worker_loop(self):
        """工作器主循环 - 使用原子任务预留防止竞争条件"""
        while self._running:
            try:
                # 检查当前活跃任务数，防止资源泄漏
                async with self._tasks_lock:
                    active_count = len(self._active_tasks)

                # 硬限制检查：如果活跃任务数超过硬限制，等待后再继续
                if active_count >= self._max_tasks_hard_limit:
                    log_info(f"[TaskWorker] 达到硬限制: {active_count}/{self._max_tasks_hard_limit} 任务，等待...")
                    await asyncio.sleep(0.5)
                    continue

                # 计算可获取的新任务数（考虑并发限制）
                max_concurrent = self.task_queue.max_concurrent
                available_slots = max_concurrent - active_count

                if available_slots <= 0:
                    # 已达到最大并发，等待一会儿
                    await asyncio.sleep(0.5)
                    continue

                # 使用原子操作预留任务，防止竞争条件
                # 每次只获取一个任务，确保原子性
                reserved_tasks = []
                for _ in range(max(1, available_slots)):
                    task = self.task_queue.repository.reserve_pending_task()
                    if task:
                        reserved_tasks.append(task)
                    else:
                        break

                if reserved_tasks:
                    log_info(f"[TaskWorker] 原子预留 {len(reserved_tasks)} 个任务，当前活跃: {active_count}")

                    # 创建并发任务列表
                    processing_tasks = []
                    for task in reserved_tasks:
                        processing_tasks.append(self._process_task_with_semaphore(task))

                    if processing_tasks:
                        # 并发执行所有任务（不等待完成，让它们并行运行）
                        await asyncio.gather(*processing_tasks, return_exceptions=True)
                else:
                    # 没有任务时等待
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                log_error(f"[TaskWorker] Error in worker loop: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _process_task_with_semaphore(self, task: Task):
        """使用信号量包装任务处理，确保并发控制（带活跃任务跟踪）"""
        async with self._processing_semaphore:
            # 创建任务并跟踪
            task_coro = self._process_task(task)
            task_obj = asyncio.create_task(task_coro)

            async with self._tasks_lock:
                self._active_tasks.add(task_obj)
                log_info(f"[TaskWorker] 任务 {task.id} 开始处理，活跃任务数: {len(self._active_tasks)}")

            try:
                await task_obj
            finally:
                async with self._tasks_lock:
                    self._active_tasks.discard(task_obj)
                    log_info(f"[TaskWorker] 任务 {task.id} 完成，活跃任务数: {len(self._active_tasks)}")

    async def _process_task(self, task: Task):
        """
        处理单个任务

        Args:
            task: 任务对象
        """
        task_id = task.id
        log_info(f"[TaskWorker] Processing task {task_id}")

        try:
            # 更新任务状态为处理中
            self.task_queue.repository.update(
                task_id,
                status=TaskStatus.PROCESSING,
                current_step='开始处理',
                progress=0
            )

            # 通知回调
            self.task_queue._notify_callbacks(
                self.task_queue.repository.get_by_id(task_id)
            )

            # 执行实际处理（在线程池中运行同步代码）
            await asyncio.to_thread(self._execute_processing, task)

            # 处理完成
            self.task_queue._notify_callbacks(
                self.task_queue.repository.get_by_id(task_id)
            )

        except Exception as e:
            log_error(f"[TaskWorker] Task {task_id} failed: {e}")
            import traceback
            log_error(f"Task error traceback:\n{traceback.format_exc()}")
            self.task_queue.repository.fail_task(task_id, str(e))
            self.task_queue._notify_callbacks(
                self.task_queue.repository.get_by_id(task_id)
            )

    def _execute_processing(self, task: Task):
        """
        新版处理逻辑：
        1. 优先处理PDF，提取结构和内容作为参考
        2. 然后处理SRT/TXT，用PDF参考生成笔记
        3. 如果没有PDF，直接处理SRT/TXT
        4. 如果启用了思维导图，生成并保存
        """
        import os
        from ..config import config_manager
        from ..llm import LLMFactory
        from .simple_processor import SimpleProcessor
        from pathlib import Path

        # 输出目录（支持环境变量覆盖，方便容器化部署）
        OUTPUT_BASE = Path(os.environ.get("OUTPUT_DIR") or
                           (Path(__file__).parent.parent.parent.parent / "output"))
        OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

        task_id = task.id
        logger = TaskLogger(task_id)

        try:
            logger.info("开始处理任务", provider=task.llm_provider, model=task.llm_model, export_mindmap=task.export_mindmap)

            # 步骤1: 初始化 LLM
            self._update_progress(task_id, 10, '初始化', '正在初始化AI模型...')
            logger.info("初始化LLM配置")

            # 获取LLM配置：优先使用任务指定的提供商，否则使用默认配置
            if task.llm_provider:
                llm_config = config_manager.get_provider_config(task.llm_provider)
                logger.info(f"使用任务指定提供商: {task.llm_provider}")
            else:
                llm_config = config_manager.get_llm_config()

            # 如果任务指定了模型，覆盖配置中的模型
            if task.llm_model:
                llm_config['model'] = task.llm_model
                logger.info(f"使用任务指定模型: {task.llm_model}")

            logger.debug(f"LLM配置: {llm_config}")

            try:
                llm = LLMFactory.create(llm_config.pop('provider'), llm_config)
                logger.info("LLM初始化成功")
            except Exception as e:
                logger.error(f"LLM初始化失败: {e}")
                raise

            # 步骤2: 使用简化处理器
            self._update_progress(task_id, 20, '开始处理', '正在分析课程内容...')

            # 加载配置中的PDF水印设置
            full_config = config_manager.load()
            pdf_watermarks = getattr(full_config, 'pdf_watermarks', None)
            if pdf_watermarks is None:
                pdf_watermarks = {'enabled': False, 'patterns': []}
                logger.info("PDF水印配置: enabled=False, patterns_count=0 (使用默认配置)")
            else:
                # Pydantic 模型对象，直接访问属性
                logger.info(f"PDF水印配置: enabled={pdf_watermarks.enabled}, patterns_count={len(pdf_watermarks.patterns)}")

            processor = SimpleProcessor(llm, {'pdf_watermarks': pdf_watermarks}, logger=logger)

            # 确定字幕文件
            subtitle_file = task.srt_file or task.txt_file
            pdf_file = task.pdf_file

            logger.info(f"处理文件: subtitle={subtitle_file}, pdf={pdf_file}")

            # 检查文件是否存在
            if subtitle_file and not Path(subtitle_file).exists():
                raise FileNotFoundError(f"字幕文件不存在: {subtitle_file}")
            if pdf_file and not Path(pdf_file).exists():
                raise FileNotFoundError(f"PDF文件不存在: {pdf_file}")

            # 步骤3: 处理生成Markdown
            if pdf_file:
                self._update_progress(task_id, 30, '分析PDF', '正在分析PDF课件结构和内容...')
                logger.info("开始分析PDF")
            else:
                self._update_progress(task_id, 30, '处理内容', '正在处理课程内容...')
                logger.info("开始处理字幕")

            try:
                markdown_content = processor.process(subtitle_file, pdf_file)
                logger.info(f"处理完成，生成Markdown长度: {len(markdown_content)} 字符")
            except Exception as e:
                logger.error(f"处理过程失败: {e}")
                raise

            # 步骤4: 生成思维导图（如果启用）
            mindmap_file = None
            mindmap_url = None

            if task.export_mindmap:
                self._update_progress(task_id, 80, '生成思维导图', '正在生成思维导图...')
                logger.info("开始生成思维导图")

                try:
                    # 准备输出路径
                    original_name = task.srt_original_name or task.txt_original_name or task_id
                    safe_base_name = secure_filename(Path(original_name).stem)
                    mindmap_output_path = OUTPUT_BASE / f"{safe_base_name}.xmind"

                    # 生成思维导图（根据配置选择格式）
                    mindmap_format = getattr(task, 'mindmap_format', 'xmind') or 'xmind'
                    mindmap_file = processor.generate_mindmap(markdown_content, mindmap_output_path, format=mindmap_format)

                    if mindmap_file and Path(mindmap_file).exists():
                        mindmap_url = f"/api/v1/process/{task_id}/download/mindmap"
                        logger.info(f"思维导图已保存: {mindmap_file}")
                    else:
                        mindmap_file = None
                        mindmap_url = None
                except Exception as e:
                    logger.error(f"思维导图生成失败: {e}")
                    # 思维导图生成失败不影响主任务完成
                    mindmap_file = None
                    mindmap_url = None

            # 步骤5: 保存Markdown
            self._update_progress(task_id, 90, '保存结果', '正在保存笔记文件...')
            # 使用安全文件名防止路径遍历攻击
            original_name = task.srt_original_name or task.txt_original_name or task_id
            safe_base_name = secure_filename(Path(original_name).stem)
            output_file = OUTPUT_BASE / f"{safe_base_name}.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                output_file.write_text(markdown_content, encoding='utf-8')
                logger.info(f"结果已保存: {output_file}")
            except Exception as e:
                logger.error(f"保存文件失败: {e}")
                raise

            # 完成
            download_url = f"/api/v1/process/{task_id}/download"
            self.task_queue.repository.complete_task(
                task_id, 
                str(output_file), 
                download_url,
                str(mindmap_file) if mindmap_file else None,
                mindmap_url
            )
            logger.info("任务完成")

        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            import traceback
            trace = traceback.format_exc()
            logger.error(f"堆栈跟踪:\n{trace}")
            raise

    def _update_progress(self, task_id: str, progress: int, step: str, message: str):
        """更新任务进度"""
        self.task_queue.update_task_progress(
            task_id,
            progress=progress,
            current_step=step,
            message=message
        )
        # 通知回调
        self.task_queue._notify_callbacks(
            self.task_queue.repository.get_by_id(task_id)
        )


# 全局工作器实例
_worker_instance: Optional[TaskWorker] = None


def get_task_worker() -> TaskWorker:
    """获取全局工作器实例"""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = TaskWorker()
    return _worker_instance


async def start_worker():
    """启动全局工作器（用于应用启动时调用）"""
    worker = get_task_worker()
    await worker.start()


async def stop_worker():
    """停止全局工作器（用于应用关闭时调用）"""
    global _worker_instance
    if _worker_instance:
        await _worker_instance.stop()
        _worker_instance = None
