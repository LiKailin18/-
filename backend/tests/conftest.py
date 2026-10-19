"""测试公共 fixture。

数据库用例的隔离方式（CLAUDE.md §11）：
外层事务 + `join_transaction_mode="create_savepoint"`。
接口里的 `commit()` 只会释放 savepoint，测试结束后整体回滚 —— 不会污染真实库。

两个 client 的区别：
- `client`     不覆盖 get_db，用于不依赖业务表的用例（如 /health）
- `db_client`  覆盖 get_db 指向测试事务，所有接口读写都在这个事务里
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.engine import engine
from app.db.session import get_db
from app.main import app
from app.models import AppUser
from app.schemas.user import UserCreate
from app.services import user_service

TEST_PASSWORD = "Test1234!"


@pytest.fixture(autouse=True)
def isolated_upload_dir(tmp_path, monkeypatch):
    """把所有测试产生的文件限制在临时目录，绝不写进仓库的 backend/storage/。"""
    target = tmp_path / "storage"
    monkeypatch.setattr(settings, "upload_dir", str(target))
    return target


@pytest.fixture(autouse=True)
def clear_setting_cache():
    """系统配置有 60 秒进程内缓存（`setting_service`）。

    缓存是**进程级**的，而用例之间只回滚数据库 —— 不清缓存的话，
    某个用例把 `ai.daily_quota` 改成 200 之后，后续用例会读到 200。
    """
    from app.services import setting_service

    setting_service._cache.clear()
    yield
    setting_service._cache.clear()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine_after_session() -> AsyncGenerator[None, None]:
    """整个测试会话结束后释放连接池，避免残留连接导致的事件循环告警。"""
    yield
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """直连 ASGI 应用的测试客户端（不走网络，不启动 lifespan）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """绑定到外层事务的会话：测试结束自动回滚。"""
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
async def db_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """所有接口共用测试事务的 client，cookie 会自动保留（refresh 用例需要）。"""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> AppUser:
    """一个已注册的普通用户（密码固定，便于登录用例复用）。"""
    return await user_service.create_user(
        db_session,
        UserCreate(
            username="test_user",
            email="test_user@example.com",
            password=TEST_PASSWORD,
            nickname="测试用户",
        ),
    )


async def login(db_client: AsyncClient, username: str, password: str) -> dict[str, str]:
    """登录并返回可直接用于请求头的 Authorization。"""
    resp = await db_client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def auth_headers(db_client: AsyncClient, test_user: AppUser) -> dict[str, str]:
    return await login(db_client, test_user.username, TEST_PASSWORD)


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> AppUser:
    """一个管理员账号（功能 13 的用例用它登录）。"""
    user = await user_service.create_user(
        db_session,
        UserCreate(
            username="test_admin",
            email="test_admin@example.com",
            password=TEST_PASSWORD,
            nickname="测试管理员",
        ),
    )
    user.role = "admin"
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_headers(db_client: AsyncClient, admin_user: AppUser) -> dict[str, str]:
    return await login(db_client, admin_user.username, TEST_PASSWORD)
