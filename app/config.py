from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Levanter FastAPI Bot"
    environment: str = "development"
    database_url: str = Field(
        description="Postgres connection string, e.g. postgresql://USER:PASSWORD@HOST/DB?sslmode=require"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
