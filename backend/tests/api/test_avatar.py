"""头像上传与访问测试（契约：docs/api.md §4）。"""

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
AVATAR_URL = "/api/v1/users/me/avatar"


async def test_upload_avatar_returns_url_and_persists(db_client, auth_headers):
    resp = await db_client.post(
        AVATAR_URL, files={"file": ("me.png", PNG_BYTES, "image/png")}, headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    url = resp.json()["avatar_url"]
    assert url.startswith("/api/v1/files/avatars/")

    me = await db_client.get("/api/v1/users/me", headers=auth_headers)
    assert me.json()["avatar_url"] == url


async def test_avatar_can_be_fetched(db_client, auth_headers):
    uploaded = await db_client.post(
        AVATAR_URL, files={"file": ("me.png", PNG_BYTES, "image/png")}, headers=auth_headers
    )
    url = uploaded.json()["avatar_url"]

    resp = await db_client.get(url, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == PNG_BYTES


async def test_avatar_requires_login(db_client, auth_headers):
    uploaded = await db_client.post(
        AVATAR_URL, files={"file": ("me.png", PNG_BYTES, "image/png")}, headers=auth_headers
    )
    url = uploaded.json()["avatar_url"]

    resp = await db_client.get(url)

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_001"


async def test_upload_avatar_rejects_non_image(db_client, auth_headers):
    resp = await db_client.post(
        AVATAR_URL, files={"file": ("me.txt", b"hello", "text/plain")}, headers=auth_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "MAT_003"


async def test_upload_avatar_rejects_fake_png(db_client, auth_headers):
    """扩展名是 .png 但文件头不对 → 拒绝。"""
    resp = await db_client.post(
        AVATAR_URL, files={"file": ("me.png", b"not a png", "image/png")}, headers=auth_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "MAT_003"


async def test_upload_avatar_rejects_too_large(db_client, auth_headers):
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 1024)

    resp = await db_client.post(
        AVATAR_URL, files={"file": ("big.png", oversized, "image/png")}, headers=auth_headers
    )

    assert resp.status_code == 413
    assert resp.json()["code"] == "MAT_002"


async def test_avatar_filename_is_validated(db_client, auth_headers):
    """不合规的文件名一律 404（阻挡目录穿越等猜测式访问）。"""
    for name in ("../../../etc/passwd", "not-a-uuid.png", "abc.png"):
        resp = await db_client.get(f"/api/v1/files/avatars/{name}", headers=auth_headers)
        assert resp.status_code == 404, name
