"""
EventBus tests
"""

import asyncio
import pytest
from vid2note_core.events.bus import EventBus, TaskEvent


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EventBus()
    q = bus.subscribe("task_abc")
    event = TaskEvent(task_id="task_abc", event_type="node.completed", node_name="download")
    bus.publish(event)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.event_type == "node.completed"
    assert received.node_name == "download"
    bus.unsubscribe("task_abc", q)


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = EventBus()
    q1 = bus.subscribe("task_multi")
    q2 = bus.subscribe("task_multi")
    event = TaskEvent(task_id="task_multi", event_type="task.started")
    bus.publish(event)
    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.event_type == "task.started"
    assert r2.event_type == "task.started"
    bus.unsubscribe("task_multi", q1)
    bus.unsubscribe("task_multi", q2)


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    bus = EventBus()
    q = bus.subscribe("task_unsub")
    bus.unsubscribe("task_unsub", q)
    bus.publish(TaskEvent(task_id="task_unsub", event_type="node.completed"))
    # Should not receive anything; queue is removed
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.2)


@pytest.mark.asyncio
async def test_queue_full_drops_event():
    bus = EventBus()
    q = bus.subscribe("task_full")
    # Fill queue to capacity
    for i in range(100):
        bus.publish(TaskEvent(task_id="task_full", event_type="node.started"))
    # One more should be dropped without error
    bus.publish(TaskEvent(task_id="task_full", event_type="node.started"))
    assert q.qsize() == 100
    bus.unsubscribe("task_full", q)


def test_task_event_to_sse_payload():
    event = TaskEvent(
        task_id="task_123",
        event_type="node.completed",
        node_name="download",
        progress=25,
        message="下载完成",
    )
    payload = event.to_sse_payload()
    assert payload.startswith("data: ")
    assert '"task_id": "task_123"' in payload
    assert '"event_type": "node.completed"' in payload
    assert '"progress": 25' in payload
