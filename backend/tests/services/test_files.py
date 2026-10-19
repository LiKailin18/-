"""文件工具单元测试（编码还原、文件名清洗、路径安全）。"""

import pytest

from app.core.exceptions import AppError
from app.utils.files import fix_filename_encoding, resolve_safe, sanitize_filename


def test_sanitize_keeps_chinese_and_spaces():
    assert sanitize_filename("高数 第一章（笔记）.docx") == "高数 第一章（笔记）.docx"


def test_sanitize_removes_path_separators():
    """路径分隔符必须被替换，否则可能被当作子目录（配合 resolve_safe 双保险）。"""
    cleaned = sanitize_filename("../../etc/passwd")

    assert "/" not in cleaned
    assert "\\" not in cleaned


def test_sanitize_strips_control_chars():
    assert sanitize_filename("a\x00b\x1fc.pdf") == "a_b_c.pdf"


def test_sanitize_falls_back_for_empty_name():
    assert sanitize_filename(None) == "unnamed"
    assert sanitize_filename("   ") == "unnamed"


def test_fix_filename_encoding_restores_mojibake():
    """模拟 HTTP 头按 latin-1 解码后的中文文件名。"""
    original = "高数第一章.docx"
    mojibake = original.encode("utf-8").decode("latin-1")

    assert fix_filename_encoding(mojibake) == original


def test_fix_filename_encoding_is_noop_for_ascii():
    assert fix_filename_encoding("calculus.pdf") == "calculus.pdf"


def test_resolve_safe_rejects_traversal():
    with pytest.raises(AppError):
        resolve_safe("../outside.txt")
