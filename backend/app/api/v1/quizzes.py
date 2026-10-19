"""AI 测试题接口（契约：docs/api.md §11）—— 功能 9。

路径按契约分布：生成在 `/ai/quizzes`，管理在 `/quizzes`，答卷在 `/quizzes/{id}/attempts`。
"""

import uuid

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_404, ERR_429, ERR_502, ERR_504
from app.schemas.ai import (
    QuizAttemptCreate,
    QuizAttemptOut,
    QuizBrief,
    QuizCreate,
    QuizOut,
    QuizQuestionOut,
)
from app.schemas.common import Page
from app.services import quiz_service

router = APIRouter(
    tags=["AI 测试题"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
        status.HTTP_429_TOO_MANY_REQUESTS: ERR_429,
        status.HTTP_504_GATEWAY_TIMEOUT: ERR_504,
    },
)

AI_ERRORS = {status.HTTP_400_BAD_REQUEST: ERR_400, status.HTTP_502_BAD_GATEWAY: ERR_502}


def _quiz_out(quiz, *, with_answer: bool = True) -> QuizOut:
    questions = [
        QuizQuestionOut(
            no=item["no"],
            type=item["type"],
            stem=item["stem"],
            options=item.get("options", []),
            answer=item.get("answer") if with_answer else None,
            explanation=item.get("explanation") if with_answer else None,
            difficulty=item.get("difficulty", "medium"),
            knowledge=item.get("knowledge", ""),
            source_hint=item.get("source_hint"),
        )
        for item in quiz.question_data
    ]
    return QuizOut(
        id=quiz.id,
        material_id=quiz.material_id,
        title=quiz.title,
        question_count=quiz.question_count,
        types=quiz.types,
        difficulty=quiz.difficulty,
        questions=questions,
        model=quiz.model,
        prompt_tokens=quiz.prompt_tokens,
        completion_tokens=quiz.completion_tokens,
        latency_ms=quiz.latency_ms,
        created_at=quiz.created_at,
    )


@router.post(
    "/ai/quizzes",
    summary="生成测试题",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizOut,
    responses=AI_ERRORS,
)
async def create_quiz(
    payload: QuizCreate, current_user: CurrentUser, db: DbSession
) -> QuizOut:
    quiz, _retries = await quiz_service.generate(db, user=current_user, data=payload)
    return _quiz_out(quiz)


@router.get("/quizzes", summary="测试题列表", response_model=Page[QuizBrief])
async def list_quizzes(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    material_id: uuid.UUID | None = None,
) -> Page[QuizBrief]:
    """列表**不含题目与答案**，防止未答题就看到答案。"""
    rows, total = await quiz_service.list_quizzes(
        db, user_id=current_user.id, offset=page.offset, limit=page.size, material_id=material_id
    )
    return Page[QuizBrief](
        items=[QuizBrief.model_validate(row) for row in rows],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get("/quizzes/{quiz_id}", summary="测试题详情", response_model=QuizOut)
async def get_quiz(
    quiz_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    with_answer: bool = True,
) -> QuizOut:
    """`with_answer=false` 时把答案与解析置空 —— 答题页用它，避免前端拿到答案。"""
    quiz = await quiz_service.get_owned(db, current_user.id, quiz_id)
    return _quiz_out(quiz, with_answer=with_answer)


@router.delete("/quizzes/{quiz_id}", summary="删除测试题", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(quiz_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    quiz = await quiz_service.get_owned(db, current_user.id, quiz_id)
    await quiz_service.delete_quiz(db, quiz)


@router.post(
    "/quizzes/{quiz_id}/attempts",
    summary="提交答卷",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizAttemptOut,
)
async def submit_attempt(
    quiz_id: uuid.UUID,
    payload: QuizAttemptCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> QuizAttemptOut:
    quiz = await quiz_service.get_owned(db, current_user.id, quiz_id)
    return await quiz_service.submit_attempt(db, user=current_user, quiz=quiz, data=payload)


@router.get(
    "/quizzes/{quiz_id}/attempts", summary="答卷记录", response_model=Page[QuizAttemptOut]
)
async def list_attempts(
    quiz_id: uuid.UUID, current_user: CurrentUser, db: DbSession, page: PageParams
) -> Page[QuizAttemptOut]:
    await quiz_service.get_owned(db, current_user.id, quiz_id)
    rows, total = await quiz_service.list_attempts(
        db, user_id=current_user.id, quiz_id=quiz_id, offset=page.offset, limit=page.size
    )
    items = [
        QuizAttemptOut(
            id=row.id,
            quiz_id=row.quiz_id,
            score=float(row.score),
            correct_count=row.correct_count,
            question_count=row.question_count,
            duration_seconds=row.duration_seconds,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return Page[QuizAttemptOut](items=items, total=total, page=page.page, size=page.size)


@router.get("/attempts/{attempt_id}", summary="答卷详情", response_model=QuizAttemptOut)
async def get_attempt(
    attempt_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> QuizAttemptOut:
    row = await quiz_service.get_attempt(db, current_user.id, attempt_id)
    return QuizAttemptOut(
        id=row.id,
        quiz_id=row.quiz_id,
        score=float(row.score),
        correct_count=row.correct_count,
        question_count=row.question_count,
        duration_seconds=row.duration_seconds,
        created_at=row.created_at,
    )
