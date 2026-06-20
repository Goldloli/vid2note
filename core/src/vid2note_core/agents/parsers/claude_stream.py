from __future__ import annotations

import json

from vid2note_core.agents.parsers.common import NativeEvent, ParserDiagnostic


class ClaudeStreamParser:
    def __init__(self):
        self.diagnostics: list[ParserDiagnostic] = []

    def parse_line(self, line: str) -> list[NativeEvent]:
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            self.diagnostics.append(ParserDiagnostic("invalid_native_event", line[:200]))
            return []
        if not isinstance(value, dict):
            return self._unknown(line)
        event_type = value.get("type")
        if event_type == "system" and value.get("subtype") == "init":
            return [NativeEvent("session", {"native_session_id": str(value.get("session_id", ""))})]
        if event_type == "assistant":
            message = value.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            events: list[NativeEvent] = []
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "thinking":
                    events.append(NativeEvent("thinking", {"text": str(item.get("thinking", ""))}))
                elif item.get("type") == "text":
                    events.append(NativeEvent("message", {"text": str(item.get("text", ""))}))
                elif item.get("type") == "tool_use":
                    events.append(NativeEvent("tool.started", {"tool": str(item.get("name", ""))}))
                elif item.get("type") == "tool_result":
                    events.append(
                        NativeEvent("tool.completed", {"tool": str(item.get("tool_use_id", ""))})
                    )
            return events
        if event_type == "result":
            if value.get("subtype") == "success":
                usage = value.get("usage")
                payload = usage if isinstance(usage, dict) else {}
                return [NativeEvent("usage", payload), NativeEvent("completed", {})]
            message = str(value.get("error", "failed"))
            code = (
                "AGENT_RESUME_MISSING"
                if "No conversation found" in message
                else "AGENT_RUNTIME_FAILED"
            )
            return [NativeEvent("failed", {"code": code, "message": message})]
        return self._unknown(line)

    def _unknown(self, line: str) -> list[NativeEvent]:
        self.diagnostics.append(ParserDiagnostic("unknown_native_event", line[:200]))
        return []
