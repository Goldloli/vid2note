"""Export the FastAPI schema with deterministic formatting."""

import argparse
import json
from pathlib import Path

from vid2note_server.main import create_app


def export_schema(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True)
    destination.write_text(payload + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export_schema(args.destination)


if __name__ == "__main__":
    main()
