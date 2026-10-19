"""文档解析单元测试（不需要数据库）。"""

from pathlib import Path

import pymupdf
import pytest
from docx import Document

from app.utils.doc_parser import DocumentParseError, clean_text, parse_document


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))
    return path


def make_pdf(path: Path, page_texts: list[str]) -> Path:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=14)
    document.save(str(path))
    document.close()
    return path


def test_parse_docx_extracts_paragraph_text(tmp_path: Path):
    path = make_docx(tmp_path / "note.docx", ["高等数学 第一章", "极限的定义与性质"])

    parsed = parse_document(path, ".docx")

    assert "高等数学" in parsed.text
    assert "极限的定义" in parsed.text
    assert parsed.char_count == len(parsed.text)
    assert parsed.page_count is None  # DOCX 没有页的概念
    assert parsed.is_scanned is False


def test_parse_pdf_counts_pages(tmp_path: Path):
    """每页放足量文字，避免被「扫描版」启发式误判（阈值 20 字符/页）。"""
    body = "Chapter One " * 20
    path = make_pdf(tmp_path / "book.pdf", [body, body])

    parsed = parse_document(path, ".pdf")

    assert parsed.page_count == 2
    assert "Chapter One" in parsed.text
    assert parsed.is_scanned is False


def test_scanned_pdf_is_flagged(tmp_path: Path):
    """没有文本层的 PDF → is_scanned=True，由上层标记 unsupported（不抛错）。"""
    path = make_pdf(tmp_path / "scan.pdf", ["", ""])

    parsed = parse_document(path, ".pdf")

    assert parsed.page_count == 2
    assert parsed.char_count == 0
    assert parsed.is_scanned is True


def test_corrupted_pdf_raises_parse_error(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not a real pdf\n")

    with pytest.raises(DocumentParseError):
        parse_document(path, ".pdf")


def test_unsupported_extension_raises(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(DocumentParseError):
        parse_document(path, ".txt")


def test_clean_text_normalizes_whitespace():
    raw = "line1   \r\n\r\n\r\n\r\nline2\x00\x07end"

    cleaned = clean_text(raw)

    assert cleaned == "line1\n\nline2end"
