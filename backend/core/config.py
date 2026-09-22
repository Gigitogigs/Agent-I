from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Autonomi Support System"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:ForcaBarca%402026!@localhost:5432/support_system"
    POSTGRES_CHECKPOINTER_SCHEMA: str = "checkpoints"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    JWT_SECRET: str = "supersecretkey_change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AES-256 key for encrypting provider API keys at rest.
    # Must be a 64-character hex string (32 bytes). Generate with:
    # python -c "import secrets; print(secrets.token_hex(32))"
    ENCRYPTION_KEY: str = "change_me_64_hex_chars_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # Used to construct password-reset links in emails.
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
