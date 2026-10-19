"""应用配置：所有可变项都从环境变量读取，代码中不出现任何密钥。

约定见 CLAUDE.md §9：
- 只提交 .env.example，.env 不入 Git
- 运行时可调的项（AI 开关、每日配额）走 app_setting 表，不走 .env
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "smart-learning-system"
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "0.1.0"
    app_timezone: str = "Asia/Shanghai"

    # ---- 安全 ----
    secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "sl_refresh"
    refresh_cookie_path: str = "/api/v1/auth"

    # ---- 数据库 ----
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/smart_learning"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ---- 文件上传 ----
    upload_dir: str = "./storage"
    max_upload_mb: int = 20

    # ---- 大模型 ----
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: int = 60
    llm_max_retries: int = 2
    llm_max_input_chars: int = 30000

    # ---- AI 行为 ----
    llm_max_steps: int = 12
    ai_agent_timeout: int = 90
    ai_use_deep_agent: bool = False
    ai_enable_note_tool: bool = False
    ai_daily_quota: int = 100

    # ---- CORS ----
    # 开发期前端可能是 localhost 或 127.0.0.1，两个都要放行：
    # 它同时用于 CORS 与 refresh/logout 的 Origin 校验（CSRF 防护）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的配置拆成列表。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
