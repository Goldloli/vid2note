"""Prompt templates"""

from pathlib import Path

_DIR = Path(__file__).parent


def _load(name: str) -> str:
    return (_DIR / f"{name}.txt").read_text(encoding="utf-8")


PDF_STRUCTURE_ANALYSIS = _load("pdf_structure_analysis")
GENERATE_WITH_PDF_REFERENCE = _load("generate_with_pdf_reference")
GENERATE_DIRECTLY = _load("generate_directly")
MINDMAP_GENERATION = _load("mindmap")
MINDMAP_OUTLINE = _load("mindmap_outline")
CLASSIFY = _load("classify")
RESTRUCTURE = _load("restructure")

__all__ = [
    "PDF_STRUCTURE_ANALYSIS",
    "GENERATE_WITH_PDF_REFERENCE",
    "GENERATE_DIRECTLY",
    "MINDMAP_GENERATION",
    "MINDMAP_OUTLINE",
    "CLASSIFY",
    "RESTRUCTURE",
]
