"""用户与认证业务逻辑（功能 1、2）。

只用 db + 参数，不碰 Request/HTTP；错误抛 app.core.exceptions 里的业务异常。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountDisabled,
    EmailTaken,
    InvalidCredentials,
    UsernameTaken,
    WrongOldPassword,
)
from app.core.security import hash_password, verify_password
from app.models import AppUser, utcnow
from app.schemas.user import PasswordChangeIn, UserCreate, UserUpdate


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> AppUser | None:
    return await db.get(AppUser, user_id)


async def get_by_username(db: AsyncSession, username: str) -> AppUser | None:
    result = await db.execute(select(AppUser).where(AppUser.username == username))
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> AppUser | None:
    result = await db.execute(select(AppUser).where(AppUser.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: UserCreate) -> AppUser:
    """注册。邮箱统一存小写，避免同名不同大小写重复注册。"""
    email = data.email.lower()

    # 先查再插：本项目未引入 Redis，直接查库即可（唯一约束仍是最终防线）
    if await get_by_username(db, data.username):
        raise UsernameTaken
    if await get_by_email(db, email):
        raise EmailTaken

    user = AppUser(
        username=data.username,
        email=email,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> AppUser:
    """登录校验。

    先验密码再看启用状态：这样「账号被禁用」的信息只透露给知道密码的人，
    否则等于给攻击者提供了账号枚举的旁路。
    """
    user = await get_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials

    if not user.is_active:
        raise AccountDisabled(f"账号已被禁用：{user.disabled_reason or '请联系管理员'}")

    user.last_login_at = utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def update_profile(db: AsyncSession, user: AppUser, data: UserUpdate) -> AppUser:
    """PATCH 语义：只改提交过的字段（exclude_unset）。"""
    changes = data.model_dump(exclude_unset=True)

    if changes.get("email"):
        email = str(changes["email"]).lower()
        if email != user.email and await get_by_email(db, email):
            raise EmailTaken
        changes["email"] = email

    for field, value in changes.items():
        setattr(user, field, value)

    user.updated_at = utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(db: AsyncSession, user: AppUser, data: PasswordChangeIn) -> None:
    """改密码并把 token_version +1 —— 该用户全部旧令牌立即失效（契约要求）。"""
    if not verify_password(data.old_password, user.password_hash):
        raise WrongOldPassword

    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    user.updated_at = utcnow()
    await db.commit()
