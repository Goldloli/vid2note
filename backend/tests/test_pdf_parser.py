"""PDFParser 的 pypdf 兼容与错误边界测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.errors import FileNotDecryptedError, PdfReadError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.parsers.pdf_parser import PDFParser


def _write_text_pdf(path: Path, page_texts: list[str], *, outline: bool = False) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)

    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        resources = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(stream)

    if outline:
        writer.add_outline_item("Overview", page_number=0)
        if len(page_texts) > 1:
            writer.add_outline_item("Details", page_number=1)

    with path.open("wb") as stream:
        writer.write(stream)


def test_parse_extracts_multiple_pages_chapters_and_full_text(tmp_path):
    path = tmp_path / "slides.pdf"
    _write_text_pdf(path, ["1. Overview", "1.1 Details"])

    result = PDFParser().parse(str(path), extract_images=True)

    assert result["total_pages"] == 2
    assert [page.page_num for page in result["pages"]] == [1, 2]
    assert [page.images for page in result["pages"]] == [[], []]
    assert "1. Overview" in result["full_text"]
    assert "1.1 Details" in result["full_text"]
    assert [(chapter.title, chapter.level, chapter.page_num) for chapter in result["chapters"]] == [
        ("1. Overview", 3, 1),
        ("1.1 Details", 2, 2),
    ]


def test_get_outline_and_extract_page_range(tmp_path):
    path = tmp_path / "outline.pdf"
    _write_text_pdf(path, ["First", "Second"], outline=True)
    parser = PDFParser()

    assert parser.get_outline(str(path)) == [
        {"level": 1, "title": "Overview", "page": 1},
        {"level": 1, "title": "Details", "page": 2},
    ]
    assert "First" not in parser.extract_text_by_pages(str(path), 1, 2)
    assert "Second" in parser.extract_text_by_pages(str(path), 1, 2)


def test_blank_pdf_returns_empty_text_without_inventing_content(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)

    result = PDFParser().parse(str(path))

    assert result["total_pages"] == 1
    assert result["pages"][0].text == ""
    assert result["full_text"] == ""
    assert result["chapters"] == []


def test_corrupted_pdf_raises_parse_error(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot-a-valid-document")

    with pytest.raises(PdfReadError):
        PDFParser().parse(str(path))


def test_encrypted_pdf_is_rejected(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("password")
    with path.open("wb") as stream:
        writer.write(stream)

    with pytest.raises((FileNotDecryptedError, PdfReadError)):
        PDFParser().parse(str(path))


def test_parser_source_has_no_pymupdf_dependency():
    source = Path(__file__).parents[1] / "src" / "parsers" / "pdf_parser.py"
    text = source.read_text(encoding="utf-8").lower()

    assert "import fitz" not in text
    assert "pymupdf" not in text
