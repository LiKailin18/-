"""管理端内容管理（契约：docs/api.md §16.3）。

关注三件事：列表不泄露大字段（正文/答案）、下架是软删除且历史数据不受影响、
每个写操作都留下审计。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Material, Note, Quiz

MATERIALS_URL = "/api/v1/admin/materials"
NOTES_URL = "/api/v1/admin/notes"
QUIZZES_URL = "/api/v1/admin/quizzes"
AUDIT_URL = "/api/v1/admin/audit-logs"


async def seed_material(db_session: AsyncSession, user_id: uuid.UUID, **overrides) -> Material:
    data = {
        "user_id": user_id,
        "title": "违规资料",
        "file_name": "bad.pdf",
        "file_ext": ".pdf",
        "mime_type": "application/pdf",
        "size_bytes": 2048,
        "file_path": "materials/nonexistent-bad.pdf",
        "file_hash": "c" * 64,
        "parse_status": "success",
        "extracted_text": "正文内容" * 100,
        "char_count": 400,
    }
    data.update(overrides)
    material = Material(**data)
    db_session.add(material)
    await db_session.commit()
    await db_session.refresh(material)
    return material


async def seed_note(db_session: AsyncSession, user_id: uuid.UUID) -> Note:
    note = Note(user_id=user_id, title="违规笔记", content="正文很长" * 100)
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


async def seed_quiz(db_session: AsyncSession, user_id: uuid.UUID) -> Quiz:
    quiz = Quiz(
        user_id=user_id,
        title="违规测试题",
        question_count=1,
        types=["single"],
        difficulty="medium",
        question_data=[
            {
                "no": 1,
                "type": "single",
                "stem": "答案是 A 的题",
                "options": ["A", "B", "C", "D"],
                "answer": ["A"],
                "difficulty": "medium",
                "knowledge": "极限",
            }
        ],
        model="stub",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    return quiz


# ------------------------------------------------------------------ 列表


async def test_material_list_shows_owner_without_content(
    db_client, admin_headers, db_session, test_user
):
    await seed_material(db_session, test_user.id)

    resp = await db_client.get(f"{MATERIALS_URL}?keyword=违规", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["owner"]["username"] == "test_user"
    assert item["title"] == "违规资料"
    assert item["parse_status"] == "success"
    # 正文绝不进列表
    assert "extracted_text" not in item


async def test_material_list_filters(db_client, admin_headers, db_session, test_user):
    await seed_material(db_session, test_user.id, title="成功解析", parse_status="success")
    await seed_material(
        db_session, test_user.id, title="解析失败", parse_status="failed", file_ext=".docx"
    )

    failed = await db_client.get(
        f"{MATERIALS_URL}?parse_status=failed&user_id={test_user.id}", headers=admin_headers
    )
    only_docx = await db_client.get(f"{MATERIALS_URL}?file_ext=.docx", headers=admin_headers)

    assert [item["title"] for item in failed.json()["items"]] == ["解析失败"]
    assert all(item["file_ext"] == ".docx" for item in only_docx.json()["items"])


async def test_note_list_returns_excerpt_only(db_client, admin_headers, db_session, test_user):
    note = await seed_note(db_session, test_user.id)

    resp = await db_client.get(f"{NOTES_URL}?user_id={test_user.id}", headers=admin_headers)

    assert resp.status_code == 200
    item = next(row for row in resp.json()["items"] if row["id"] == str(note.id))
    assert "content" not in item
    assert len(item["excerpt"]) <= 120
    assert item["owner"]["username"] == "test_user"


async def test_quiz_list_hides_questions(db_client, admin_headers, db_session, test_user):
    quiz = await seed_quiz(db_session, test_user.id)

    resp = await db_client.get(f"{QUIZZES_URL}?user_id={test_user.id}", headers=admin_headers)

    assert resp.status_code == 200
    item = next(row for row in resp.json()["items"] if row["id"] == str(quiz.id))
    assert "questions" not in item
    assert "question_data" not in item
    assert item["question_count"] == 1


# ------------------------------------------------------------------ 下架 / 重解析


async def test_admin_delete_material_is_soft_and_audited(
    db_client, admin_headers, db_session, test_user
):
    material = await seed_material(db_session, test_user.id)

    resp = await db_client.delete(f"{MATERIALS_URL}/{material.id}", headers=admin_headers)

    assert resp.status_code == 204
    await db_session.refresh(material)
    assert material.deleted_at is not None  # 软删除，行还在

    logs = await db_client.get(
        f"{AUDIT_URL}?action=material.delete&size=100", headers=admin_headers
    )
    assert any(item["target_id"] == str(material.id) for item in logs.json()["items"])

    # 用户端也不该再看到它
    listing = await db_client.get(MATERIALS_URL, headers=admin_headers)
    assert str(material.id) not in [item["id"] for item in listing.json()["items"]]


async def test_admin_delete_note_and_quiz(
    db_client, admin_headers, db_session, test_user
):
    note = await seed_note(db_session, test_user.id)
    quiz = await seed_quiz(db_session, test_user.id)

    note_deleted = await db_client.delete(f"{NOTES_URL}/{note.id}", headers=admin_headers)
    quiz_deleted = await db_client.delete(f"{QUIZZES_URL}/{quiz.id}", headers=admin_headers)
    assert note_deleted.status_code == 204
    assert quiz_deleted.status_code == 204

    await db_session.refresh(note)
    await db_session.refresh(quiz)
    assert note.deleted_at is not None
    assert quiz.deleted_at is not None

    actions = [
        item["action"]
        for item in (
            await db_client.get(AUDIT_URL, headers=admin_headers)
        ).json()["items"]
    ]
    assert "note.delete" in actions
    assert "quiz.delete" in actions


async def test_quiz_delete_keeps_attempts_counted(
    db_client, admin_headers, db_session, test_user
):
    """下架的题不再出现，但历史答卷仍在（统计口径不随下架变化）。"""
    quiz = await seed_quiz(db_session, test_user.id)
    from app.models import QuizAttempt

    db_session.add(
        QuizAttempt(
            quiz_id=quiz.id,
            user_id=test_user.id,
            answers=[{"no": 1, "answer": ["A"], "is_correct": True}],
            score=100,
            correct_count=1,
            question_count=1,
        )
    )
    await db_session.commit()

    await db_client.delete(f"{QUIZZES_URL}/{quiz.id}", headers=admin_headers)

    # 答卷还在
    attempts = await db_client.get(
        f"/api/v1/quizzes/{quiz.id}/attempts", headers=admin_headers
    )
    # 题目被下架后，用户端该卷的答卷列表按「题不存在」处理 → 404 也合理；
    # 这里只断言「答卷行没有被删」
    from sqlalchemy import func, select

    count = await db_session.scalar(
        select(func.count()).select_from(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id)
    )
    assert int(count or 0) == 1
    assert attempts.status_code in (200, 404)


async def test_reparse_material_sets_pending_and_audits(
    db_client, admin_headers, db_session, test_user, monkeypatch
):
    material = await seed_material(db_session, test_user.id, parse_status="failed")

    # 别真的去解析文件（它本来就不存在）：把后台任务换掉
    from app.services import material_service

    async def _noop(_material_id):  # pragma: no cover - 只为了不被调用
        return None

    monkeypatch.setattr(material_service, "parse_material", _noop)

    resp = await db_client.post(
        f"{MATERIALS_URL}/{material.id}/reparse", headers=admin_headers
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending"
    await db_session.refresh(material)
    assert material.parse_status == "pending"
    assert material.parse_error is None

    logs = await db_client.get(
        f"{AUDIT_URL}?action=material.reparse&size=100", headers=admin_headers
    )
    assert any(item["target_id"] == str(material.id) for item in logs.json()["items"])


async def test_unknown_content_returns_404(db_client, admin_headers):
    missing = uuid.uuid4()

    for url in (
        f"{MATERIALS_URL}/{missing}",
        f"{NOTES_URL}/{missing}",
        f"{QUIZZES_URL}/{missing}",
    ):
        resp = await db_client.delete(url, headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "SYS_404"

    reparse = await db_client.post(f"{MATERIALS_URL}/{missing}/reparse", headers=admin_headers)
    assert reparse.status_code == 404


async def test_content_endpoints_require_admin(db_client, auth_headers, db_session, test_user):
    material = await seed_material(db_session, test_user.id)

    listing = await db_client.get(MATERIALS_URL, headers=auth_headers)
    deleting = await db_client.delete(f"{MATERIALS_URL}/{material.id}", headers=auth_headers)

    assert listing.status_code == 403
    assert deleting.status_code == 403
