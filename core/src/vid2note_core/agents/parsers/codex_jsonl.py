from __future__ import annotations

import json

from vid2note_core.agents.parsers.common import NativeEvent, ParserDiagnostic


class CodexJsonlParser:
    def __init__(self):
        self.diagnostics: list[ParserDiagnostic] = []

    def parse_line(self, line: str) -> list[NativeEvent]:
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            self.diagnostics.append(ParserDiagnostic("invalid_native_event", line[:200]))
            return []
        if not isinstance(value, dict):
            self.diagnostics.append(ParserDiagnostic("invalid_native_event", line[:200]))
            return []
        event_type = value.get("type")
        if event_type == "thread.started":
            return [NativeEvent("session", {"native_session_id": str(value.get("thread_id"))})]
        if event_type in {"turn.started", "item.started"}:
            return []
        if event_type == "item.completed":
            item = value.get("item")
            if not isinstance(item, dict):
                return self._unknown(line)
            item_type = item.get("type")
            if item_type == "reasoning":
                return [NativeEvent("thinking", {"text": str(item.get("text", ""))})]
            if item_type == "agent_message":
                return [NativeEvent("message", {"text": str(item.get("text", ""))})]
            if item_type == "file_change":
                return [NativeEvent("file", {"path": str(item.get("path", ""))})]
            if item_type == "command_execution":
                return [NativeEvent("tool.completed", {"tool": "command_execution"})]
            return self._unknown(line)
        if event_type == "turn.completed":
            usage = value.get("usage")
            payload = usage if isinstance(usage, dict) else {}
            return [NativeEvent("usage", payload), NativeEvent("completed", {})]
        if event_type in {"turn.failed", "error"}:
            error = value.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            return [
                NativeEvent(
                    "failed",
                    {"code": "AGENT_RUNTIME_FAILED", "message": str(message or "failed")},
                )
            ]
        return self._unknown(line)

    def _unknown(self, line: str) -> list[NativeEvent]:
        self.diagnostics.append(ParserDiagnostic("unknown_native_event", line[:200]))
        return []
