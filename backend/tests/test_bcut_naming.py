"""实验性在线 ASR 的内部与外部命名约束。"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IGNORED_PARTS = {
    ".beads",
    ".codegraph",
    ".git",
    ".venv",
    "data",
    "dist",
    "node_modules",
}


def test_legacy_online_asr_identifier_is_fully_removed():
    legacy_identifier = "asr" + "tools"
    matches: list[str] = []

    for path in REPO_ROOT.rglob("*"):
        relative = path.relative_to(REPO_ROOT)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if legacy_identifier in relative.as_posix().lower():
            matches.append(relative.as_posix())
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if legacy_identifier in content.lower():
            matches.append(relative.as_posix())

    assert matches == []
