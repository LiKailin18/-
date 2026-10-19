"""学习资料接口测试（契约：docs/api.md §5）—— 功能 3。

后台解析的处理：用 monkeypatch 把 material_service.parse_material 换成
「用测试 session 解析」，这样解析仍发生在测试事务内，用例结束自动回滚。
"""

import io
import uuid

import pymupdf
import pytest
from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Material
from app.services import material_service
from tests.conftest import TEST_PASSWORD, login

MATERIALS_URL = "/api/v1/materials"

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ------------------------------------------------------------------ 工具


def docx_bytes(*paragraphs: str) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def pdf_bytes(*page_texts: str) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=14)
    data = document.tobytes()
    document.close()
    return data


def upload_files(name: str, content: bytes, mime: str) -> dict:
    return {"file": (name, content, mime)}


@pytest.fixture
def inline_parse(monkeypatch, db_session: AsyncSession):
    """让 BackgroundTasks 用测试 session 解析（默认实现会另开连接，看不到未提交数据）。

    必须先保存原函数引用：monkeypatch 之后模块属性已被替换，
    在 stub 里再通过 material_service.parse_material 调用会递归到自己。
    """
    original = material_service.parse_material

    async def _parse(material_id: uuid.UUID) -> None:
        await original(material_id, db=db_session)

    monkeypatch.setattr(material_service, "parse_material", _parse)


# ------------------------------------------------------------------ 上传与解析


async def test_upload_docx_parses_and_returns_contract_fields(
    db_client, auth_headers, inline_parse
):
    resp = await db_client.post(
        MATERIALS_URL,
        files=upload_files("高数笔记.docx", docx_bytes("第一章 极限", "定义与性质"), DOCX_MIME),
        data={"subject": "高数", "tags": "极限,定义"},
        headers=auth_headers,
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["title"] == "高数笔记"  # 缺省取文件名（不含扩展名）
    assert body["subject"] == "高数"
    assert body["tags"] == ["极限", "定义"]
    assert body["file_ext"] == ".docx"
    assert body["size_bytes"] > 0
    # 契约：列表/详情不返回正文
    assert "extracted_text" not in body
    assert "file_path" not in body

    # 后台解析已经完成（BackgroundTasks 在响应后执行，httpx 会等它结束）
    detail = await db_client.get(f"{MATERIALS_URL}/{body['id']}", headers=auth_headers)
    parsed = detail.json()
    assert parsed["parse_status"] == "success"
    assert parsed["char_count"] > 0
    assert parsed["page_count"] is None


async def test_upload_pdf_reports_page_count(db_client, auth_headers, inline_parse):
    page = "Chapter One content line. " * 20
    resp = await db_client.post(
        MATERIALS_URL,
        files=upload_files("book.pdf", pdf_bytes(page, page), "application/pdf"),
        headers=auth_headers,
    )

    assert resp.status_code == 202
    material_id = resp.json()["id"]

    detail = await db_client.get(f"{MATERIALS_URL}/{material_id}", headers=auth_headers)
    assert detail.json()["parse_status"] == "success"
    assert detail.json()["page_count"] == 2


async def test_scanned_pdf_marked_unsupported(db_client, auth_headers, inline_parse):
    """扫描版不是错误：返回 202，状态为 unsupported，前端提示不支持 OCR。"""
    resp = await db_client.post(
        MATERIALS_URL,
        files=upload_files("scan.pdf", pdf_bytes("", ""), "application/pdf"),
        headers=auth_headers,
    )

    assert resp.status_code == 202
    detail = await db_client.get(f"{MATERIALS_URL}/{resp.json()['id']}", headers=auth_headers)
    assert detail.json()["parse_status"] == "unsupported"
    assert "OCR" in detail.json()["parse_error"]


async def test_upload_rejects_unsupported_extension(db_client, auth_headers):
    resp = await db_client.post(
        MATERIALS_URL,
        files=upload_files("note.txt", b"hello", "text/plain"),
        headers=auth_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "MAT_003"


async def test_upload_rejects_fake_pdf(db_client, auth_headers):
    """扩展名是 .pdf 但文件头不是 %PDF- → 拒绝（防伪装文件）。"""
    resp = await db_client.post(
        MATERIALS_URL,
        files=upload_files("fake.pdf", b"just plain text", "application/pdf"),
        headers=auth_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "MAT_003"


async def test_upload_rejects_too_large_file(db_client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = docx_bytes("x" * 2000) + b"\x00" * (1 * 1024 * 1024 + 1024)

    resp = await db_client.post(
        MATERIALS_URL, files=upload_files("big.docx", big, DOCX_MIME), headers=auth_headers
    )

    assert resp.status_code == 413
    assert resp.json()["code"] == "MAT_002"


# ------------------------------------------------------------------ 列表 / 详情 / 修改


async def test_list_supports_pagination_and_filters(
    db_client, auth_headers, inline_parse
):
    for index in range(3):
        await db_client.post(
            MATERIALS_URL,
            files=upload_files(f"m{index}.docx", docx_bytes(f"内容 {index}"), DOCX_MIME),
            data={"subject": "高数" if index < 2 else "英语"},
            headers=auth_headers,
        )

    page1 = await db_client.get(f"{MATERIALS_URL}?page=1&size=2", headers=auth_headers)
    assert page1.status_code == 200
    body = page1.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["size"] == 2
    assert len(body["items"]) == 2

    by_subject = await db_client.get(f"{MATERIALS_URL}?subject=英语", headers=auth_headers)
    assert by_subject.json()["total"] == 1

    by_keyword = await db_client.get(f"{MATERIALS_URL}?keyword=m1", headers=auth_headers)
    assert by_keyword.json()["total"] == 1

    by_status = await db_client.get(
        f"{MATERIALS_URL}?parse_status=success", headers=auth_headers
    )
    assert by_status.json()["total"] == 3


async def test_patch_material_updates_fields(db_client, auth_headers, inline_parse):
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("a.docx", docx_bytes("hi"), DOCX_MIME),
        headers=auth_headers,
    )
    material_id = created.json()["id"]

    resp = await db_client.patch(
        f"{MATERIALS_URL}/{material_id}",
        json={"title": "改名后的资料", "subject": "线代", "tags": ["矩阵", "行列式"]},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "改名后的资料"
    assert resp.json()["subject"] == "线代"
    assert resp.json()["tags"] == ["矩阵", "行列式"]


# ------------------------------------------------------------------ 正文分片


async def test_read_text_chunk_offsets(db_client, auth_headers, inline_parse):
    text = "0123456789"
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("digits.docx", docx_bytes(text), DOCX_MIME),
        headers=auth_headers,
    )
    material_id = created.json()["id"]

    first = await db_client.get(
        f"{MATERIALS_URL}/{material_id}/text?offset=0&limit=4", headers=auth_headers
    )
    assert first.status_code == 200
    body = first.json()
    assert body["text"] == "0123"
    assert body["total_chars"] == 10
    assert body["has_more"] is True

    tail = await db_client.get(
        f"{MATERIALS_URL}/{material_id}/text?offset=8&limit=4", headers=auth_headers
    )
    assert tail.json()["text"] == "89"
    assert tail.json()["has_more"] is False


# ------------------------------------------------------------------ 下载


async def test_download_returns_file_with_attachment_header(
    db_client, auth_headers, inline_parse
):
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("笔记.docx", docx_bytes("content"), DOCX_MIME),
        headers=auth_headers,
    )
    material_id = created.json()["id"]

    resp = await db_client.get(f"{MATERIALS_URL}/{material_id}/download", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"  # docx 是 zip
    assert "attachment" in resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]


# ------------------------------------------------------------------ 重解析 / 删除


async def test_reparse_rejected_for_successful_material(
    db_client, auth_headers, inline_parse
):
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("ok.docx", docx_bytes("fine"), DOCX_MIME),
        headers=auth_headers,
    )

    resp = await db_client.post(
        f"{MATERIALS_URL}/{created.json()['id']}/reparse", headers=auth_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_400"


async def test_reparse_allowed_for_failed_material(
    db_client, db_session: AsyncSession, auth_headers, inline_parse
):
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("bad.docx", docx_bytes("whatever"), DOCX_MIME),
        headers=auth_headers,
    )
    material = await db_session.get(Material, uuid.UUID(created.json()["id"]))
    material.parse_status = "failed"
    material.parse_error = "模拟失败"
    await db_session.commit()

    resp = await db_client.post(
        f"{MATERIALS_URL}/{created.json()['id']}/reparse", headers=auth_headers
    )

    assert resp.status_code == 202


async def test_delete_soft_deletes_and_removes_file(
    db_client, db_session: AsyncSession, auth_headers, inline_parse
):
    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("todelete.docx", docx_bytes("bye"), DOCX_MIME),
        headers=auth_headers,
    )
    material_id = created.json()["id"]
    material = await db_session.get(Material, uuid.UUID(material_id))
    from app.utils import files as files_util

    stored_path = files_util.resolve_safe(material.file_path)
    assert stored_path.is_file()

    deleted = await db_client.delete(f"{MATERIALS_URL}/{material_id}", headers=auth_headers)
    assert deleted.status_code == 204

    gone = await db_client.get(f"{MATERIALS_URL}/{material_id}", headers=auth_headers)
    assert gone.status_code == 404
    assert not stored_path.exists()


# ------------------------------------------------------------------ 越权隔离


async def test_material_is_isolated_between_users(
    db_client, db_session: AsyncSession, auth_headers, inline_parse
):
    """A 的资料，B 既读不到也下不了、删不掉 —— 一律 404（不暴露存在性）。"""
    from app.schemas.user import UserCreate
    from app.services import user_service

    created = await db_client.post(
        MATERIALS_URL,
        files=upload_files("private.docx", docx_bytes("secret"), DOCX_MIME),
        headers=auth_headers,
    )
    material_id = created.json()["id"]

    await user_service.create_user(
        db_session,
        UserCreate(username="intruder", email="intruder@example.com", password=TEST_PASSWORD),
    )
    intruder_headers = await login(db_client, "intruder", TEST_PASSWORD)

    for method, url in (
        ("get", f"{MATERIALS_URL}/{material_id}"),
        ("get", f"{MATERIALS_URL}/{material_id}/download"),
        ("get", f"{MATERIALS_URL}/{material_id}/text"),
        ("delete", f"{MATERIALS_URL}/{material_id}"),
    ):
        resp = await getattr(db_client, method)(url, headers=intruder_headers)
        assert resp.status_code == 404, f"{method} {url} 应为 404，实际 {resp.status_code}"
        assert resp.json()["code"] == "SYS_404"
