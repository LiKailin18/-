"""管理端用户管理（功能 13.2；契约：docs/api.md §16.2）。

三条安全规则（都在 `update_user` 里收口）：

1. **不能操作自己**：禁用 / 降级 / 重置密码 / 强制下线自己 → 400 `ADMIN_001`
   （防的是把系统锁死，而不是信任管理员的自制力）
2. **变更即下线**：`is_active` 或 `role` 变化 → `token_version + 1`，旧令牌立即失效
3. **禁用必填原因**：`is_active=false` 时 `disabled_reason` 必填，该文案会展示给用户

列表的 counts 用**相关子查询**一次取回（禁止 N+1）。
"""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AdminSelfOperation, BadRequest, NotFound
from app.core.security import hash_password
from app.models import (
    AiUsage,
    AppUser,
    Material,
    Note,
    QuizAttempt,
    StudyRecord,
    utcnow,
)
from app.services import audit_service

ORDER_FIELDS = {"created_at", "username", "last_login_at"}

_PASSWORD_ALPHABET = string.ascii_letters + string.digits


async def _get_target(db: AsyncSession, user_id: uuid.UUID) -> AppUser:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise NotFound("用户不存在")
    return user


def _counts_subqueries(days: int = 30):
    """列表用的四个相关子查询（一条 SQL 取回，不做逐行查询）。"""
    since = datetime.now(UTC) - timedelta(days=days)
    return {
        "materials": select(func.count())
        .select_from(Material)
        .where(Material.user_id == AppUser.id, Material.deleted_at.is_(None))
        .scalar_subquery(),
        "notes": select(func.count())
        .select_from(Note)
        .where(Note.user_id == AppUser.id, Note.deleted_at.is_(None))
        .scalar_subquery(),
        "ai_calls_30d": select(func.count())
        .select_from(AiUsage)
        .where(AiUsage.user_id == AppUser.id, AiUsage.created_at >= since)
        .scalar_subquery(),
        "study_minutes_30d": select(func.coalesce(func.sum(StudyRecord.duration_minutes), 0))
        .where(
            StudyRecord.user_id == AppUser.id,
            StudyRecord.deleted_at.is_(None),
            StudyRecord.started_at >= since,
        )
        .scalar_subquery(),
    }


async def list_users(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    keyword: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    order: str = "-created_at",
) -> tuple[list[dict], int]:
    """用户列表：分页 + 关键词 + 角色/状态筛选；counts 一次聚合取回。"""
    conditions = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                AppUser.username.ilike(pattern),
                AppUser.email.ilike(pattern),
                AppUser.nickname.ilike(pattern),
            )
        )
    if role:
        conditions.append(AppUser.role == role)
    if is_active is not None:
        conditions.append(AppUser.is_active.is_(is_active))

    total = await db.scalar(select(func.count()).select_from(AppUser).where(*conditions))

    descending = order.startswith("-")
    field = order.lstrip("-")
    column = getattr(AppUser, field) if field in ORDER_FIELDS else AppUser.created_at
    order_by = column.desc() if descending else column.asc()

    counts = _counts_subqueries()
    rows = (
        await db.execute(
            select(
                AppUser,
                counts["materials"].label("materials"),
                counts["notes"].label("notes"),
                counts["ai_calls_30d"].label("ai_calls_30d"),
                counts["study_minutes_30d"].label("study_minutes_30d"),
            )
            .where(*conditions)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.AppUser.id,
            "username": row.AppUser.username,
            "email": row.AppUser.email,
            "nickname": row.AppUser.nickname,
            "role": row.AppUser.role,
            "is_active": row.AppUser.is_active,
            "disabled_reason": row.AppUser.disabled_reason,
            "created_at": row.AppUser.created_at,
            "last_login_at": row.AppUser.last_login_at,
            "counts": {
                "materials": int(row.materials or 0),
                "notes": int(row.notes or 0),
                "ai_calls_30d": int(row.ai_calls_30d or 0),
                "study_minutes_30d": int(row.study_minutes_30d or 0),
            },
        }
        for row in rows
    ]
    return items, int(total or 0)


async def get_detail(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """详情：在列表字段基础上，补答题正确率与 AI token。"""
    user = await _get_target(db, user_id)
    since = datetime.now(UTC) - timedelta(days=30)

    materials = await db.scalar(
        select(func.count())
        .select_from(Material)
        .where(Material.user_id == user_id, Material.deleted_at.is_(None))
    )
    notes = await db.scalar(
        select(func.count())
        .select_from(Note)
        .where(Note.user_id == user_id, Note.deleted_at.is_(None))
    )
    ai_calls = await db.scalar(
        select(func.count())
        .select_from(AiUsage)
        .where(AiUsage.user_id == user_id, AiUsage.created_at >= since)
    )
    ai_tokens = await db.scalar(
        select(func.coalesce(func.sum(AiUsage.total_tokens), 0)).where(
            AiUsage.user_id == user_id, AiUsage.created_at >= since
        )
    )
    minutes = await db.scalar(
        select(func.coalesce(func.sum(StudyRecord.duration_minutes), 0)).where(
            StudyRecord.user_id == user_id,
            StudyRecord.deleted_at.is_(None),
            StudyRecord.started_at >= since,
        )
    )
    quiz = (
        await db.execute(
            select(
                func.count().label("attempts"),
                func.coalesce(func.sum(QuizAttempt.correct_count), 0).label("correct"),
                func.coalesce(func.sum(QuizAttempt.question_count), 0).label("questions"),
            ).where(QuizAttempt.user_id == user_id, QuizAttempt.created_at >= since)
        )
    ).one()
    quiz_attempts = int(quiz.attempts or 0)
    questions = int(quiz.questions or 0)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "nickname": user.nickname,
        "role": user.role,
        "is_active": user.is_active,
        "disabled_reason": user.disabled_reason,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "counts": {
            "materials": int(materials or 0),
            "notes": int(notes or 0),
            "ai_calls_30d": int(ai_calls or 0),
            "study_minutes_30d": int(minutes or 0),
        },
        "quiz_accuracy_30d": (
            round(int(quiz.correct or 0) / questions, 4) if questions else 0.0
        ),
        "quiz_attempts_30d": quiz_attempts,
        "ai_tokens_30d": int(ai_tokens or 0),
    }


async def update_user(
    db: AsyncSession,
    *,
    admin: AppUser,
    user_id: uuid.UUID,
    is_active: bool | None,
    role: str | None,
    disabled_reason: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AppUser:
    """改启用状态 / 角色；**不 commit**（审计在同一事务里，由调用方提交）。"""
    user = await _get_target(db, user_id)

    # 规则 1：不能对自己做危险操作
    if user.id == admin.id:
        if is_active is False:
            raise AdminSelfOperation("不能禁用自己的账号")
        if role is not None and role != user.role:
            raise AdminSelfOperation("不能修改自己的角色")

    if role is not None and role not in ("user", "admin"):
        raise BadRequest("角色只能是 user 或 admin")

    # 规则 3：禁用必填原因
    if is_active is False:
        reason = (disabled_reason or "").strip()
        if not reason:
            raise BadRequest("禁用用户时必须填写原因（会展示给该用户）")
        if len(reason) > 200:
            raise BadRequest("禁用原因不能超过 200 字")

    changed: dict = {}

    if is_active is not None and is_active != user.is_active:
        was_active = user.is_active
        before_reason = user.disabled_reason
        if is_active:
            user.is_active = True
            user.disabled_at = None
            user.disabled_reason = None
        else:
            user.is_active = False
            user.disabled_at = utcnow()
            user.disabled_reason = (disabled_reason or "").strip()
        user.token_version += 1  # 规则 2：变更即下线
        changed["is_active"] = is_active
        audit_service.write_log(
            db,
            admin_id=admin.id,
            action=(
                audit_service.ACTION_USER_ENABLE
                if is_active
                else audit_service.ACTION_USER_DISABLE
            ),
            target_type="user",
            target_id=user.id,
            detail={
                "from": {"is_active": was_active, "disabled_reason": before_reason},
                "to": {
                    "is_active": is_active,
                    "disabled_reason": user.disabled_reason,
                },
            },
            ip=ip,
            user_agent=user_agent,
        )

    if role is not None and role != user.role:
        before_role = user.role
        user.role = role
        user.token_version += 1  # 规则 2：变更即下线
        changed["role"] = role
        audit_service.write_log(
            db,
            admin_id=admin.id,
            action=audit_service.ACTION_USER_ROLE_CHANGE,
            target_type="user",
            target_id=user.id,
            detail={"from": {"role": before_role}, "to": {"role": role}},
            ip=ip,
            user_agent=user_agent,
        )

    if not changed:
        # 没有任何变更就不写库（但也不报错，幂等）
        return user

    user.updated_at = utcnow()
    db.add(user)
    await db.flush()
    return user


def _random_password(length: int = 12) -> str:
    """12 位随机密码：大小写 + 数字（不含易混淆字符，管理员要线下转达）。"""
    ambiguous = set("O0Il1")
    alphabet = [ch for ch in _PASSWORD_ALPHABET if ch not in ambiguous]
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def reset_password(
    db: AsyncSession,
    *,
    admin: AppUser,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    """重置为随机密码；返回明文（**仅此一次**），并强制下线。"""
    user = await _get_target(db, user_id)
    if user.id == admin.id:
        raise AdminSelfOperation("不能重置自己的密码")

    password = _random_password()
    user.password_hash = hash_password(password)
    user.token_version += 1
    user.updated_at = utcnow()
    db.add(user)

    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_USER_RESET_PASSWORD,
        target_type="user",
        target_id=user.id,
        detail={"username": user.username},
        ip=ip,
        user_agent=user_agent,
    )
    await db.flush()
    return password


async def revoke_tokens(
    db: AsyncSession,
    *,
    admin: AppUser,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """强制下线（token_version + 1）。"""
    user = await _get_target(db, user_id)
    if user.id == admin.id:
        raise AdminSelfOperation("不能强制自己下线")

    user.token_version += 1
    user.updated_at = utcnow()
    db.add(user)

    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_USER_REVOKE_TOKENS,
        target_type="user",
        target_id=user.id,
        detail={"username": user.username},
        ip=ip,
        user_agent=user_agent,
    )
    await db.flush()
