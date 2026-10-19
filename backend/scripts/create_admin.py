"""创建 / 提升管理员账号（功能 13 的引导入口）。

为什么需要脚本：管理端接口一律要求 `role='admin'`，而「第一个管理员」没有任何
管理员可以帮他创建 —— 否则只能手工改库。这是**运维入口**，不是业务接口，
所以放在 scripts 下，不进 HTTP 层。

用法（在 backend 目录下）：

    # 把已有用户提升为管理员
    .venv\\Scripts\\python scripts\\create_admin.py --promote zhangsan

    # 新建一个管理员（不存在则创建，存在则提升 + 改密码）
    .venv\\Scripts\\python scripts\\create_admin.py \\
        --username admin --email admin@example.com --password Admin1234!

不带参数时打印当前管理员列表。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.security import hash_password
from app.db.engine import SessionLocal
from app.models import AppUser, utcnow


async def list_admins() -> None:
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(AppUser).where(AppUser.role == "admin").order_by(AppUser.username)
            )
        ).scalars().all()
        if not rows:
            print("当前没有管理员账号。用 --promote <username> 提升一个，或用 --username 新建。")
            return
        print(f"当前管理员（{len(rows)} 个）：")
        for row in rows:
            flag = "启用" if row.is_active else "已禁用"
            print(f"  - {row.username} <{row.email}> {flag}")


async def promote(username: str, email: str | None, password: str | None) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(AppUser).where(AppUser.username == username))

        if user is None:
            if not email or not password:
                print(f"用户 {username} 不存在；新建管理员需要同时给 --email 与 --password")
                return
            user = AppUser(
                username=username,
                email=email,
                password_hash=hash_password(password),
                nickname=username,
                role="admin",
            )
            db.add(user)
            print(f"已创建管理员 {username} <{email}>")
        else:
            user.role = "admin"
            user.is_active = True
            user.disabled_at = None
            user.disabled_reason = None
            if password:
                user.password_hash = hash_password(password)
                print(f"已把 {username} 提升为管理员并重置密码")
            else:
                print(f"已把 {username} 提升为管理员（密码未改动）")

        # 角色变了 → 旧令牌立即失效（与接口里的规则一致）
        user.token_version += 1
        user.updated_at = utcnow()
        db.add(user)
        await db.commit()

        print(f"完成：{user.username} role={user.role} token_version={user.token_version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="创建或提升管理员账号")
    parser.add_argument("--promote", metavar="USERNAME", help="把已有用户提升为管理员")
    parser.add_argument("--username", help="要新建/更新的用户名")
    parser.add_argument("--email", help="邮箱（新建时必填）")
    parser.add_argument("--password", help="密码（可选；给了就重置）")
    args = parser.parse_args()

    if args.promote:
        asyncio.run(promote(args.promote, args.email, args.password))
    elif args.username:
        asyncio.run(promote(args.username, args.email, args.password))
    else:
        asyncio.run(list_admins())


if __name__ == "__main__":
    main()
