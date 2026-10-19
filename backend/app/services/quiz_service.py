"""AI 测试题生成与判分（功能 9）。"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import usage as usage_module
from app.ai.schemas import QuizOut
from app.ai.validators import QuizInvalidError, normalize_quiz
from app.core.config import settings
from app.core.exceptions import NotFound
from app.models import AppUser, Quiz, QuizAttempt
from app.schemas.ai import AttemptDetail, QuizAttemptCreate, QuizAttemptOut, QuizCreate
from app.services import ai_common, material_service
from app.services.summary_service import _ensure_parsable  # 同一套资料状态校验

TYPE_HINTS = {
    "single": "单选题（4 个选项，唯一正确答案）",
    "multiple": "多选题（4 个选项，至少 2 个正确答案）",
    "judge": "判断题",
    "blank": "填空题",
}


def _message(material_title: str, text: str, data: QuizCreate) -> str:
    types = "、".join(TYPE_HINTS[item] for item in data.types)
    return (
        f"资料标题：{material_title}\n"
        f"出题要求：共 {data.count} 道题，题型为 {types}，难度 {data.difficulty}。\n\n"
        f"请基于下面的正文出题（可用 read_material_chunk 继续读取更多内容）：\n"
        f"-----\n{text}\n-----"
    )


async def generate(db: AsyncSession, *, user: AppUser, data: QuizCreate) -> tuple[Quiz, int]:
    await usage_module.ensure_quota(db, user_id=user.id)

    material = await material_service.get_owned(db, user.id, data.material_id)
    _ensure_parsable(material)

    text = (material.extracted_text or "")[data.scope_start : data.scope_end or None]
    if not text.strip():
        raise QuizInvalidError("资料正文为空，无法出题")

    expected_types = list(dict.fromkeys(data.types))

    def validator(result: QuizOut) -> QuizOut:
        return normalize_quiz(
            result, expected_count=data.count, expected_types=expected_types
        )

    result, usage, retries = await ai_common.structured_with_retry(
        "quiz",
        user_id=user.id,
        db=db,
        message=_message(material.title, text[: settings.llm_max_input_chars], data),
        validator=validator,
        invalid_errors=(QuizInvalidError,),
    )

    quiz = Quiz(
        user_id=user.id,
        material_id=material.id,
        title=(data.title or f"{material.title} 测验")[:200],
        question_count=len(result.questions),
        types=expected_types,
        difficulty=data.difficulty,
        question_data=[question.model_dump() for question in result.questions],
        model=settings.llm_model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)

    await usage_module.record_usage(
        db, user_id=user.id, scene="quiz", model=settings.llm_model, usage=usage
    )
    return quiz, retries


async def list_quizzes(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    material_id: uuid.UUID | None = None,
) -> tuple[list[Quiz], int]:
    conditions = [Quiz.user_id == user_id, Quiz.deleted_at.is_(None)]
    if material_id:
        conditions.append(Quiz.material_id == material_id)

    total = await db.scalar(select(func.count()).select_from(Quiz).where(*conditions))
    rows = (
        await db.execute(
            select(Quiz)
            .where(*conditions)
            .order_by(Quiz.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def get_owned(db: AsyncSession, user_id: uuid.UUID, quiz_id: uuid.UUID) -> Quiz:
    quiz = await db.scalar(
        select(Quiz).where(
            Quiz.id == quiz_id, Quiz.user_id == user_id, Quiz.deleted_at.is_(None)
        )
    )
    if quiz is None:
        raise NotFound("测试题不存在")
    return quiz


async def delete_quiz(db: AsyncSession, quiz: Quiz) -> None:
    from app.models import utcnow

    quiz.deleted_at = utcnow()
    quiz.updated_at = utcnow()
    await db.commit()


# --------------------------------------------------------------------- 判分


def _normalize(values: list[str]) -> list[str]:
    return sorted(value.strip().lower() for value in values if value.strip())


def judge_question(question: dict, answer: list[str]) -> bool:
    """判分规则（契约 §11）：

    - 单选 / 判断：全等
    - 多选：**完全一致**才算对（少选不得分）
    - 填空：去空白 + 忽略大小写后比较
    """
    correct = question.get("answer") or []
    if question.get("type") == "blank":
        return _normalize(correct) == _normalize(answer)
    if question.get("type") == "multiple":
        return set(correct) == set(answer)
    return len(answer) == 1 and answer[0].strip().lower() == str(correct[0]).strip().lower()


async def submit_attempt(
    db: AsyncSession, *, user: AppUser, quiz: Quiz, data: QuizAttemptCreate
) -> QuizAttemptOut:
    questions = {int(item["no"]): item for item in quiz.question_data}
    submitted = {item.no: item.answer for item in data.answers}

    details: list[AttemptDetail] = []
    details_rows: list[dict] = []
    correct_count = 0

    for no in sorted(questions):
        question = questions[no]
        answer = submitted.get(no, [])
        is_correct = judge_question(question, answer)
        correct_count += 1 if is_correct else 0
        details.append(
            AttemptDetail(
                no=no,
                your_answer=answer,
                correct_answer=question.get("answer") or [],
                is_correct=is_correct,
                explanation=question.get("explanation"),
            )
        )
        details_rows.append({"no": no, "answer": answer, "is_correct": is_correct})

    total = len(questions) or 1
    score = Decimal(str(round(correct_count / total * 100, 1)))

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        answers=details_rows,
        score=score,
        correct_count=correct_count,
        question_count=len(questions),
        duration_seconds=data.duration_seconds,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return QuizAttemptOut(
        id=attempt.id,
        quiz_id=quiz.id,
        score=float(attempt.score),
        correct_count=attempt.correct_count,
        question_count=attempt.question_count,
        duration_seconds=attempt.duration_seconds,
        created_at=attempt.created_at,
        details=details,
    )


async def list_attempts(
    db: AsyncSession, *, user_id: uuid.UUID, quiz_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[QuizAttempt], int]:
    conditions = [QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz_id]
    total = await db.scalar(select(func.count()).select_from(QuizAttempt).where(*conditions))
    rows = (
        await db.execute(
            select(QuizAttempt)
            .where(*conditions)
            .order_by(QuizAttempt.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def get_attempt(db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID) -> QuizAttempt:
    attempt = await db.scalar(
        select(QuizAttempt).where(
            QuizAttempt.id == attempt_id, QuizAttempt.user_id == user_id
        )
    )
    if attempt is None:
        raise NotFound("答卷不存在")
    return attempt
