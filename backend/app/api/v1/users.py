"""用户接口（契约：docs/api.md §4）—— 功能 2。

这里能拿到的 current_user 一定是「令牌有效 + token_version 一致 + 账号启用」的，
不需要在接口里重复校验权限。
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.core.deps import CurrentUser, DbSession
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_409, ERR_413
from app.models import utcnow
from app.schemas.material import AvatarOut
from app.schemas.user import PasswordChangeIn, UserOut, UserUpdate
from app.services import user_service
from app.utils import files

router = APIRouter(
    prefix="/users",
    tags=["用户"],
    responses={status.HTTP_401_UNAUTHORIZED: ERR_401, status.HTTP_403_FORBIDDEN: ERR_403},
)


@router.get("/me", summary="获取我的信息", response_model=UserOut)
async def read_me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch(
    "/me",
    summary="修改我的信息",
    response_model=UserOut,
    responses={status.HTTP_409_CONFLICT: ERR_409},
)
async def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserOut:
    user = await user_service.update_profile(db, current_user, payload)
    return UserOut.model_validate(user)


@router.post(
    "/me/password",
    summary="修改密码",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def change_my_password(
    payload: PasswordChangeIn,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """改密码后该用户全部旧令牌失效，前端需重新登录（契约 §4）。"""
    await user_service.change_password(db, current_user, payload)


@router.post(
    "/me/avatar",
    summary="上传头像",
    response_model=AvatarOut,
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_413_CONTENT_TOO_LARGE: ERR_413,
    },
)
async def upload_avatar(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="PNG / JPG，≤2MB")],
) -> AvatarOut:
    """头像存本地 storage/avatars/，数据库只存 URL（契约 §4）。"""
    old_url = current_user.avatar_url

    url = await files.save_avatar(file, current_user.id)
    current_user.avatar_url = url
    current_user.updated_at = utcnow()
    await db.commit()

    # 提交成功后再删旧文件，避免事务回滚导致头像丢失
    files.delete_avatar_by_url(old_url)
    return AvatarOut(avatar_url=url)
