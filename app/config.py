from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Levanter FastAPI Bot"
    bot_name: str = "Levanter FastAPI Bot"
    environment: str = "development"
    database_url: str = Field(
        description="Postgres connection string, e.g. postgresql://USER:PASSWORD@HOST/DB?sslmode=require"
    )
    command_prefix: str = "."
    whatsapp_only: bool = True
    require_session_id: bool = True
    default_session_id: str | None = None
    admin_phone_number: str | None = None
    levanter_version: str = "5.3.3"
    levanter_plugins: int = 220
    whatsapp_api_url: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
