from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "A-bot"
    bot_name: str = "A-bot"
    environment: str = "development"
    session_token_bytes: int = 32
    max_session_id_length: int = 128
    max_session_id_generation_attempts: int = 5
    database_url: str = Field(
        description="Postgres connection string, e.g. postgresql://USER:PASSWORD@HOST/DB?sslmode=require"
    )
    command_prefix: str = "."
    whatsapp_only: bool = True
    require_session_id: bool = True
    default_session_id: str | None = None
    admin_phone_number: str | None = None
    levanter_version: str = Field(default="1.0.0", description="Display-only version text for menu header.")
    levanter_plugins: int = Field(default=220, description="Display-only plugin count text for menu header.")
    whatsapp_api_url: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
