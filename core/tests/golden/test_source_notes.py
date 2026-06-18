import re
from pathlib import Path

import pytest
import yaml
from vid2note_core.llm.mock import MockLLM

DATASET = Path(__file__).parents[3] / "tests" / "golden"


def _cases():
    manifest = yaml.safe_load((DATASET / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    return manifest["cases"]


@pytest.mark.golden
@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_mock_source_note_matches_golden_contract(case):
    transcript = (DATASET / case["transcript"]).read_text(encoding="utf-8")
    expected = yaml.safe_load((DATASET / case["expected"]).read_text(encoding="utf-8"))

    note = MockLLM().restructure_content(transcript)

    for claim in expected["required_claims"]:
        assert claim in note
    for claim in case["expects"].get("forbidden_claims", []):
        assert claim not in note

    claims = [line for line in note.splitlines() if line.startswith("- ")]
    cited = [line for line in claims if re.search(r"证据：\d\d:\d\d:\d\d–\d\d:\d\d:\d\d", line)]
    minimum = case["expects"].get("min_citation_coverage")
    if minimum is not None:
        assert len(cited) / len(claims) >= minimum
    if case["expects"].get("preserve_uncertainty"):
        assert "ASR 不确定" in note
    assert note.count("\n## ") >= case["expects"].get("min_sections", 1)
