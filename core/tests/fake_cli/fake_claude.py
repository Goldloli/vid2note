#!/usr/bin/env python3
import json
import sys

prompt = sys.stdin.read()
json.loads(prompt)
print(
    json.dumps({"type": "system", "subtype": "init", "session_id": "fake-claude"}),
    flush=True,
)
print(
    json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Compounding rewards patience."}]},
        }
    ),
    flush=True,
)
print(json.dumps({"type": "result", "subtype": "success", "usage": {}}), flush=True)
