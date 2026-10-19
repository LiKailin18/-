"""本地文件存储：校验、落盘、删除、路径安全。

设计要点（CLAUDE.md §5.1）：
- 纯工具层，不依赖数据库与 FastAPI（只依赖 UploadFile 的 read 接口）
- 所有对外路径都是**相对 upload_dir 的相对路径**，数据库只存相对路径
- 读取时用 resolve_safe 做路径穿越防护（绝不能用静态目录直接暴露）
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import AppError

# 允许的扩展名 -> 允许的 MIME（MIME 由客户端提供，只能作为辅助校验）
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
}

# 文件头魔数：PDF 是 %PDF-，DOCX 本质是 ZIP
_MAGIC = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
}

_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_CHUNK = 1024 * 1024


class FileTooLargeError(AppError):
    """413 MAT_002"""

    status_code = 413
    code = "MAT_002"
    message = "文件超过大小限制"


class UnsupportedFileTypeError(AppError):
    """400 MAT_003"""

    status_code = 400
    code = "MAT_003"
    message = "文件类型不支持，仅接受 PDF 与 DOCX"


class InvalidFileError(AppError):
    """文件头与扩展名不匹配（伪装文件）。"""

    status_code = 400
    code = "MAT_003"
    message = "文件内容与扩展名不符"


@dataclass(frozen=True)
class SavedFile:
    relative_path: str
    file_ext: str
    mime_type: str
    size_bytes: int
    file_hash: str


def upload_root() -> Path:
    """上传根目录（相对路径按 backend/ 解析）。"""
    root = Path(settings.upload_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def fix_filename_encoding(name: str) -> str:
    """还原 multipart 文件名的编码。

    HTTP 头按 latin-1 解码，而浏览器/httpx 在 Content-Disposition 里发的是**原始 UTF-8 字节**，
    所以中文文件名会变成乱码（如 '高数.docx' -> 'é«˜æ•°.docx'）。
    这里做一次 latin-1 -> utf-8 的可逆还原；不是这种情况时原样返回。
    """
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def sanitize_filename(name: str | None) -> str:
    """清洗用于展示与下载的原始文件名。

    只去掉路径分隔符、控制字符和 Windows 非法字符；
    **保留中文、空格、括号等正常字符** —— 过度清洗会把中文文件名变成一串下划线。
    """
    fixed = fix_filename_encoding((name or "").strip())
    cleaned = _FORBIDDEN_CHARS.sub("_", fixed).strip(" .")
    return cleaned[:120] or "unnamed"


def resolve_safe(relative_path: str) -> Path:
    """把相对路径解析成绝对路径，并确保它仍在 upload_dir 内。

    这是防目录穿越的唯一入口：任何来自数据库/请求的路径都必须经过它。
    """
    root = upload_root().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents and target != root:
        raise AppError("非法文件路径", code="SYS_400")
    return target


async def save_upload(
    upload: UploadFile,
    *,
    owner_id: uuid.UUID,
    subdir: str = "",
    max_bytes: int | None = None,
) -> SavedFile:
    """流式落盘并做三重校验：扩展名 → 大小 → 文件头魔数。

    先写到 .part 临时文件，全部校验通过才改名，
    避免半截文件被当成有效资料（也避免占着正式路径）。

    `max_bytes` 由调用方决定：上传上限是**可配项**（`app_setting.upload.max_mb`），
    而本模块是纯工具、拿不到 db，所以不在这里读配置。
    """
    original_name = upload.filename or ""
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError

    mime_type = (upload.content_type or "application/octet-stream").lower()
    if mime_type not in ALLOWED_MIME_TYPES[ext]:
        # 浏览器偶尔给不准（如 octet-stream），所以只对「明确错误」的 MIME 拒绝
        raise UnsupportedFileTypeError(f"文件类型不支持：{mime_type}")

    target_dir = upload_root() / subdir / str(owner_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{ext}"
    final_path = target_dir / stored_name
    temp_path = final_path.with_suffix(final_path.suffix + ".part")

    digest = hashlib.sha256()
    size = 0
    limit_bytes = max_bytes if max_bytes is not None else settings.max_upload_mb * 1024 * 1024
    limit_mb = max(1, round(limit_bytes / 1024 / 1024))
    head = b""

    try:
        with temp_path.open("wb") as fp:
            while chunk := await upload.read(_CHUNK):
                size += len(chunk)
                if size > limit_bytes:
                    raise FileTooLargeError(f"文件超过 {limit_mb} MB 限制")
                if len(head) < 8:
                    head += chunk[: 8 - len(head)]
                digest.update(chunk)
                fp.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    if size == 0:
        temp_path.unlink(missing_ok=True)
        raise InvalidFileError("文件为空")

    if not head.startswith(_MAGIC[ext]):
        temp_path.unlink(missing_ok=True)
        raise InvalidFileError

    temp_path.replace(final_path)

    relative = (Path(subdir) / str(owner_id) / stored_name).as_posix()
    return SavedFile(
        relative_path=relative,
        file_ext=ext,
        mime_type=mime_type,
        size_bytes=size,
        file_hash=digest.hexdigest(),
    )


def delete_file(relative_path: str | None) -> None:
    """删除文件；失败只记录，不阻断业务（例如资料已软删除但文件已被手动删掉）。"""
    if not relative_path:
        return
    try:
        resolve_safe(relative_path).unlink(missing_ok=True)
    except Exception:  # 清理失败不应影响主流程
        import logging

        logging.getLogger(__name__).warning("删除文件失败: %s", relative_path)


# --------------------------------------------------------------------- 头像

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_IMAGE_MAGIC = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}
AVATAR_MAX_MB = 2
AVATAR_URL_PREFIX = "/api/v1/files/avatars/"


async def save_avatar(upload: UploadFile, owner_id: uuid.UUID) -> str:
    """保存头像，返回可直接访问的 URL 路径（契约 docs/api.md §4）。

    文件名带随机后缀，避免浏览器/代理缓存旧头像。
    """
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise UnsupportedFileTypeError("头像仅支持 PNG / JPG")

    target_dir = upload_root() / "avatars"
    target_dir.mkdir(parents=True, exist_ok=True)

    size = 0
    head = b""
    data = b""
    max_bytes = AVATAR_MAX_MB * 1024 * 1024
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise FileTooLargeError(f"头像不能超过 {AVATAR_MAX_MB} MB")
        if len(head) < 8:
            head += chunk[: 8 - len(head)]
        data += chunk

    if not data:
        raise InvalidFileError("头像文件为空")
    if not head.startswith(_IMAGE_MAGIC[ext]):
        raise InvalidFileError("头像文件内容与扩展名不符")

    filename = f"{owner_id}_{uuid.uuid4().hex[:8]}{ext}"
    (target_dir / filename).write_bytes(data)
    return f"{AVATAR_URL_PREFIX}{filename}"


def delete_avatar_by_url(url: str | None) -> None:
    """按 avatar_url 反推出相对路径并删除旧头像。"""
    if not url or not url.startswith(AVATAR_URL_PREFIX):
        return
    delete_file(f"avatars/{url[len(AVATAR_URL_PREFIX):]}")
