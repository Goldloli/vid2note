from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime
from secrets import token_hex

from vid2note_core.agents.models import AgentEvent, AgentRun, AgentRunInput, AgentSession
from vid2note_core.agents.runtime import AgentRuntime
from vid2note_core.storage.db import Database

_TERMINAL = {"run.completed", "run.failed", "run.cancelled"}


class AgentSessionService:
    def __init__(self, database: Database, runtimes: dict[str, AgentRuntime]):
        self.database = database
        self.runtimes = runtimes
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)
        self._init_tables()

    def create_session(
        self,
        runtime_id: str,
        *,
        context_paths: list[str],
        model: str | None = None,
    ) -> AgentSession:
        if runtime_id not in self.runtimes:
            raise KeyError(runtime_id)
        now = datetime.now(UTC)
        session = AgentSession(
            id=f"session_{token_hex(6)}",
            runtime_id=runtime_id,
            model=model,
            context_paths=context_paths,
            status="created",
            created_at=now,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO agent_sessions "
            "(id, runtime_id, model, context_paths, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session.id,
                runtime_id,
                model,
                json.dumps(context_paths),
                session.status,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        row = self.database.fetchone("SELECT * FROM agent_sessions WHERE id = ?", (session_id,))
        if row is None:
            return None
        return AgentSession(
            id=row["id"],
            runtime_id=row["runtime_id"],
            model=row["model"],
            context_paths=json.loads(row["context_paths"]),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def send_message(self, session_id: str, message: str) -> AgentRun:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        run = AgentRun(
            id=f"run_{token_hex(6)}",
            session_id=session_id,
            status="running",
            created_at=datetime.now(UTC),
        )
        self.database.execute(
            "INSERT INTO agent_runs (id, session_id, status, created_at) VALUES (?, ?, ?, ?)",
            (run.id, session_id, run.status, run.created_at.isoformat()),
        )
        self._update_session(session_id, "running")
        task = asyncio.create_task(self._consume(session, run, message))
        self._tasks[run.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run.id, None))
        return run

    async def cancel(self, run_id: str) -> None:
        row = self.database.fetchone("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
        if row is None:
            raise KeyError(run_id)
        session = self.get_session(row["session_id"])
        if session is None:
            raise KeyError(row["session_id"])
        await self.runtimes[session.runtime_id].cancel(run_id)

    def list_events(self, session_id: str) -> list[AgentEvent]:
        rows = self.database.fetchall(
            "SELECT event_json FROM agent_events WHERE session_id = ? ORDER BY ordinal",
            (session_id,),
        )
        return [AgentEvent.model_validate_json(row["event_json"]) for row in rows]

    def subscribe(self, session_id: str) -> asyncio.Queue[AgentEvent]:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=256)
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[AgentEvent]) -> None:
        self._subscribers[session_id].discard(queue)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _consume(self, session: AgentSession, run: AgentRun, message: str) -> None:
        runtime = self.runtimes[session.runtime_id]
        terminal_seen = False
        last_sequence = -1
        try:
            async for event in runtime.run(
                AgentRunInput(
                    run_id=run.id,
                    session_id=session.id,
                    message=message,
                    context_paths=session.context_paths,
                    model=session.model,
                )
            ):
                if event.sequence <= last_sequence or terminal_seen:
                    raise RuntimeError("invalid runtime event sequence")
                last_sequence = event.sequence
                terminal_seen = event.type in _TERMINAL
                self._persist_event(session.id, event)
            if not terminal_seen:
                self._persist_event(
                    session.id,
                    AgentEvent(
                        run_id=run.id,
                        sequence=last_sequence + 1,
                        type="run.failed",
                        timestamp=datetime.now(UTC),
                        payload={"code": "AGENT_TERMINAL_MISSING"},
                    ),
                )
        except asyncio.CancelledError:
            if not terminal_seen:
                self._persist_event(
                    session.id,
                    AgentEvent(
                        run_id=run.id,
                        sequence=last_sequence + 1,
                        type="run.cancelled",
                        timestamp=datetime.now(UTC),
                        payload={},
                    ),
                )
            raise
        except Exception as exc:  # noqa: BLE001 - runtime boundary
            if not terminal_seen:
                self._persist_event(
                    session.id,
                    AgentEvent(
                        run_id=run.id,
                        sequence=last_sequence + 1,
                        type="run.failed",
                        timestamp=datetime.now(UTC),
                        payload={"code": "AGENT_RUNTIME_ERROR", "message": str(exc)},
                    ),
                )

    def _persist_event(self, session_id: str, event: AgentEvent) -> None:
        ordinal_row = self.database.fetchone(
            "SELECT COALESCE(MAX(ordinal), -1) + 1 AS value FROM agent_events WHERE session_id = ?",
            (session_id,),
        )
        ordinal = int(ordinal_row["value"])
        self.database.execute(
            "INSERT INTO agent_events (session_id, run_id, ordinal, event_json) VALUES (?, ?, ?, ?)",
            (session_id, event.run_id, ordinal, event.model_dump_json()),
        )
        if event.type in _TERMINAL:
            status = event.type.removeprefix("run.")
            now = datetime.now(UTC).isoformat()
            self.database.execute(
                "UPDATE agent_runs SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, event.run_id),
            )
            self._update_session(session_id, status)
        for queue in tuple(self._subscribers[session_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers[session_id].discard(queue)

    def _update_session(self, session_id: str, status: str) -> None:
        self.database.execute(
            "UPDATE agent_sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(UTC).isoformat(), session_id),
        )

    def _init_tables(self) -> None:
        self.database.execute(
            "CREATE TABLE IF NOT EXISTS agent_sessions ("
            "id TEXT PRIMARY KEY, runtime_id TEXT NOT NULL, model TEXT, "
            "context_paths TEXT NOT NULL, status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        self.database.execute(
            "CREATE TABLE IF NOT EXISTS agent_runs ("
            "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, completed_at TEXT)"
        )
        self.database.execute(
            "CREATE TABLE IF NOT EXISTS agent_events ("
            "session_id TEXT NOT NULL, run_id TEXT NOT NULL, ordinal INTEGER NOT NULL, "
            "event_json TEXT NOT NULL, PRIMARY KEY (session_id, ordinal))"
        )
