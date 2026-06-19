from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VaultLayout:
    root: Path
    raw: Path
    sources: Path
    wiki: Path
    assets: Path
    private: Path
    agents: Path
    index: Path
    log: Path

    @classmethod
    def initialize(cls, root: str | Path) -> VaultLayout:
        root_path = Path(root).expanduser().resolve()
        layout = cls(
            root=root_path,
            raw=root_path / "raw",
            sources=root_path / "sources",
            wiki=root_path / "wiki",
            assets=root_path / "assets",
            private=root_path / ".vid2note",
            agents=root_path / "AGENTS.md",
            index=root_path / "index.md",
            log=root_path / "log.md",
        )
        for directory in (
            layout.raw,
            layout.sources,
            layout.wiki / "concepts",
            layout.wiki / "people",
            layout.wiki / "projects",
            layout.assets,
            layout.private / "cache" / "frames",
            layout.private / "cache" / "clips",
            layout.private / "staging",
        ):
            directory.mkdir(parents=True, exist_ok=True)

        template_root = Path(__file__).parent / "templates"
        for destination, template_name in (
            (layout.agents, "AGENTS.md"),
            (layout.index, "index.md"),
            (layout.log, "log.md"),
        ):
            try:
                with destination.open("x", encoding="utf-8") as output:
                    output.write((template_root / template_name).read_text(encoding="utf-8"))
            except FileExistsError:
                pass
        return layout
