"""Standalone server entry point used by the packaged Electron application."""

import os

import uvicorn

from vid2note_server.main import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("VID2NOTE_HOST", "127.0.0.1"),
        port=int(os.environ.get("VID2NOTE_PORT", "18080")),
        log_level=os.environ.get("VID2NOTE_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
