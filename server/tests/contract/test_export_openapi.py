import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def test_export_openapi_is_deterministic(tmp_path):
    from scripts.export_openapi import export_schema

    first = export_schema(tmp_path / "a.json")
    second = export_schema(tmp_path / "b.json")

    assert first.read_bytes() == second.read_bytes()
