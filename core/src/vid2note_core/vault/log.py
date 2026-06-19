from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


class VaultLog:
    def __init__(self, path: Path):
        self.path = path

    def append_edit(
        self,
        *,
        operation: Literal["human-edit", "external-edit"],
        path: str,
        before_hash: str,
        after_hash: str,
    ) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation,
            "path": path,
            "before_hash": before_hash,
            "after_hash": after_hash,
        }
        payload = (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode()
        descriptor = os.open(self.path, os.O_APPEND | os.O_WRONLY)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
