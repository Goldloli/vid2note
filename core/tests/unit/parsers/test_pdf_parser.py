"""测试 PDF 解析器"""
from unittest.mock import MagicMock, patch
from vid2note_core.parsers.pdf_parser import PDFParser


def test_parse_mock():
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Chapter 1\nHello"
    mock_doc.__len__.return_value = 1
    mock_doc.__getitem__.return_value = mock_page
    mock_doc.get_toc.return_value = []

    with patch("fitz.open", return_value=mock_doc):
        parser = PDFParser()
        result = parser.parse("dummy.pdf")
        assert result["total_pages"] == 1
        assert "Chapter 1" in result["full_text"]
