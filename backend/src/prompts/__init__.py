"""
Prompt templates for LLM processing
"""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def _load_prompt(filename: str) -> str:
    """Load prompt template from file"""
    prompt_file = _PROMPTS_DIR / filename
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()


# PDF Structure Analysis Prompt
PDF_STRUCTURE_ANALYSIS = _load_prompt('pdf_structure_analysis.txt')

# Generate with PDF Reference Prompt
GENERATE_WITH_PDF_REFERENCE = _load_prompt('generate_with_pdf_reference.txt')

# Generate Directly Prompt (no PDF)
GENERATE_DIRECTLY = _load_prompt('generate_directly.txt')

# Mindmap Generation Prompt (Mermaid format - deprecated)
MINDMAP_GENERATION = _load_prompt('mindmap.txt')

# Mindmap Outline Prompt (for XMind format)
MINDMAP_OUTLINE = _load_prompt('mindmap_outline.txt')


__all__ = [
    'PDF_STRUCTURE_ANALYSIS',
    'GENERATE_WITH_PDF_REFERENCE',
    'GENERATE_DIRECTLY',
    'MINDMAP_GENERATION',
    'MINDMAP_OUTLINE',
]
