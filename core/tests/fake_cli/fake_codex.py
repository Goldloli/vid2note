#!/usr/bin/env python3
import json
import sys

prompt = sys.stdin.read()
print(json.dumps({"type": "thread.started", "thread_id": "fake-codex"}), flush=True)
print(
    json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "Compounding rewards patience." if prompt else "No prompt",
            },
        }
    ),
    flush=True,
)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}}), flush=True)
