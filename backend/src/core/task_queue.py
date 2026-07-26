"""
任务队列管理器
负责任务的提交、调度和状态管理
"""
import asyncio
from typing import Optional, List, Callable, Dict, Any
from datetime import datetime

try:
    from ..db import TaskRepository
except ImportError:
    from db import TaskRepository
try:
    from ..models.task import Task, TaskStatus
except ImportError:
    from models.task import Task, TaskStatus


class QueueFullError(Exception):
    """队列已满异常"""
    pass


class TaskQueue:
    """任务队列管理器"""

    def __init__(
        self,
        repository: Optional[TaskRepository] = None,
        max_concurrent: int = 3,
        max_queue_size: int = 20
    ):
        """
        初始化任务队列

        Args:
            repository: 任务仓库
            max_concurrent: 最大并发数
            max_queue_size: 队列最大容量（pending + processing）
        """
        self.repository = repository or TaskRepository()
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: dict = {}
        self._callbacks: List[Callable] = []

    def is_queue_full(self) -> bool:
        """
        检查队列是否已满

        Returns:
            队列是否已满（pending + processing >= max_queue_size）
        """
        active_count = self.repository.count_active_tasks()
        return active_count >= self.max_queue_size

    def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态

        Returns:
            队列状态信息
        """
        active_count = self.repository.count_active_tasks()
        return {
            "max_queue_size": self.max_queue_size,
            "active_count": active_count,
            "available_slots": max(0, self.max_queue_size - active_count),
            "is_full": active_count >= self.max_queue_size,
            "max_concurrent": self.max_concurrent
        }

    def submit_task(
        self,
        task_id: str,
        srt_file: Optional[str] = None,
        txt_file: Optional[str] = None,
        pdf_file: Optional[str] = None,
        srt_original_name: Optional[str] = None,
        txt_original_name: Optional[str] = None,
        pdf_original_name: Optional[str] = None,
        extract_images: bool = False,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None
    ) -> Task:
        """
        提交新任务到队列

        Args:
            task_id: 任务ID
            srt_file: SRT文件路径
            txt_file: TXT文件路径
            pdf_file: PDF文件路径
            ...

        Returns:
            创建的任务对象

        Raises:
            QueueFullError: 当队列已满时
        """
        # 检查队列是否已满
        if self.is_queue_full():
            raise QueueFullError(
                f"队列已满，当前活跃任务数: {self.repository.count_active_tasks()}, "
                f"最大容量: {self.max_queue_size}"
            )

        # 创建任务对象
        task = Task(
            id=task_id,
            status=TaskStatus.PENDING,
            srt_file=srt_file,
            txt_file=txt_file,
            pdf_file=pdf_file,
            srt_original_name=srt_original_name,
            txt_original_name=txt_original_name,
            pdf_original_name=pdf_original_name,
            extract_images=extract_images,
            llm_provider=llm_provider,
            llm_model=llm_model,
            title=srt_original_name or txt_original_name or task_id
        )

        # 保存到数据库
        self.repository.create(task)

        return task

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务对象或None
        """
        return self.repository.get_by_id(task_id)

    def update_task_progress(
        self,
        task_id: str,
        progress: int,
        current_step: str,
        message: Optional[str] = None
    ) -> bool:
        """
        更新任务进度

        Args:
            task_id: 任务ID
            progress: 进度 (0-100)
            current_step: 当前步骤
            message: 消息

        Returns:
            是否成功
        """
        return self.repository.update(
            task_id,
            progress=progress,
            current_step=current_step,
            message=message,
            updated_at=datetime.now()
        )

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        task = self.repository.get_by_id(task_id)
        if not task:
            return False

        if task.status == TaskStatus.PROCESSING:
            # 如果正在处理，需要中断
            # TODO: 实现中断逻辑
            pass

        return self.repository.cancel_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        return self.repository.delete(task_id)

    def clear_completed_tasks(self) -> int:
        """
        清空所有已完成的任务（包括已完成和失败的）

        Returns:
            删除的任务数量
        """
        return self.repository.delete_all_completed()

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        获取任务列表

        Args:
            status: 状态筛选
            limit: 数量限制

        Returns:
            任务列表
        """
        return self.repository.list_all(status=status, limit=limit)

    def get_pending_tasks(self, limit: int = 10) -> List[Task]:
        """
        获取待处理任务

        Args:
            limit: 数量限制

        Returns:
            待处理任务列表
        """
        return self.repository.get_pending_tasks(limit)

    def get_processing_count(self) -> int:
        """
        获取正在处理的任务数量

        Returns:
            数量
        """
        return self.repository.count_by_status(TaskStatus.PROCESSING)

    def register_callback(self, callback: Callable):
        """
        注册任务状态变更回调

        Args:
            callback: 回调函数
        """
        self._callbacks.append(callback)

    def _notify_callbacks(self, task: Task):
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(task)
            except Exception:
                pass


# 全局队列实例
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """获取全局任务队列实例"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
