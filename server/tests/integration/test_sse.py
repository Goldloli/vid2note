"""
SSE endpoint integration tests

event_stream 是一个无限 while True 循环（含 30s keep-alive）。直接通过
HTTP 客户端消费会阻塞到 keep-alive。这里改为直接测试 event_stream 生成器
本身：它是一个 async generator，订阅 EventBus、产出 SSE 文本块。这样能在
不等待 30s、不依赖真实 HTTP 堆栈的前提下，验证 SSE 的格式与投递逻辑。

关键点：event_stream 在第一次进入循环、调用 queue.get() 之前完成 subscribe。
所以测试要先把 __anext__ 派发成 task（驱动生成器跑到 queue.get() 阻塞点），
此时订阅已建立，再 publish 才能让它产出。
"""

import asyncio
import json
from datetime import datetime

import pytest
from vid2note_core.events.bus import EventBus, TaskEvent
from vid2note_server.api.events import event_stream


def _make_event(task_id: str, event_type: str = "task.started") -> TaskEvent:
    return TaskEvent(
        task_id=task_id,
        event_type=event_type,
        progress=0,
        message="开始",
        timestamp=datetime.now().isoformat(),
    )


async def _consume_next(gen, bus, task_id, event=None):
    """驱动生成器跑到 queue.get() 阻塞点（订阅已建立），再 publish，然后取结果。"""
    nxt = asyncio.create_task(gen.__anext__())
    # 让事件循环推进，直到生成器内部完成 subscribe 并阻塞在 queue.get()
    for _ in range(10):
        await asyncio.sleep(0)
        if task_id in bus._channels:
            break
    bus.publish(event or _make_event(task_id, "task.started"))
    return await asyncio.wait_for(nxt, timeout=5)


@pytest.mark.asyncio
async def test_event_stream_yields_published_event(monkeypatch):
    """发布事件后，event_stream 应产出对应的 SSE 文本块"""
    bus = EventBus()
    monkeypatch.setattr("vid2note_server.api.events.get_event_bus", lambda: bus)

    task_id = "task_123456789abc"
    gen = event_stream(task_id)
    try:
        chunk = await _consume_next(gen, bus, task_id)
        assert "task.started" in chunk
        assert "data: " in chunk
    finally:
        await gen.aclose()


@pytest.mark.asyncio
async def test_event_stream_keepalive_on_timeout(monkeypatch):
    """无事件时，event_stream 超时后应产出 keep-alive 注释"""
    bus = EventBus()
    monkeypatch.setattr("vid2note_server.api.events.get_event_bus", lambda: bus)
    # 把内部超时改小，避免测试真的等 30s
    import vid2note_server.api.events as events_mod

    original_wait_for = asyncio.wait_for

    async def fast_wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, 0.05)

    monkeypatch.setattr(events_mod.asyncio, "wait_for", fast_wait_for)

    task_id = "task_123456789abc"
    gen = event_stream(task_id)
    try:
        nxt = asyncio.create_task(gen.__anext__())
        chunk = await original_wait_for(nxt, timeout=5)
        assert chunk.startswith(":keep-alive")
    finally:
        await gen.aclose()


@pytest.mark.asyncio
async def test_event_stream_unsubscribes_on_close(monkeypatch):
    """生成器关闭后应从 EventBus 取消订阅"""
    bus = EventBus()
    monkeypatch.setattr("vid2note_server.api.events.get_event_bus", lambda: bus)

    task_id = "task_123456789abc"
    gen = event_stream(task_id)
    try:
        await _consume_next(gen, bus, task_id)
        assert task_id in bus._channels
    finally:
        await gen.aclose()
    # 取消订阅发生在 finally 中，需要让事件循环跑一下
    for _ in range(10):
        await asyncio.sleep(0)
        if task_id not in bus._channels:
            break
    assert task_id not in bus._channels


@pytest.mark.asyncio
async def test_event_stream_sse_payload_format(monkeypatch):
    """SSE 文本块格式应为 'data: {json}\\n\\n'"""
    bus = EventBus()
    monkeypatch.setattr("vid2note_server.api.events.get_event_bus", lambda: bus)

    task_id = "task_123456789abc"
    gen = event_stream(task_id)
    try:
        chunk = await _consume_next(gen, bus, task_id)
        assert chunk.endswith("\n\n")
        payload = chunk[len("data: ") :]
        if payload.endswith("\n\n"):
            payload = payload[:-2]
        data = json.loads(payload)
        assert data["event_type"] == "task.started"
        assert data["task_id"] == task_id
    finally:
        await gen.aclose()
