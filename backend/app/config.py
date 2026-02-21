from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "info"

    actian_vectorai_url: str | None = None
    actian_vectorai_api_key: str | None = None
    sphinx_api_key: str | None = None
    safetykit_api_key: str | None = None
    hive_api_key: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()

__all__ = ["settings", "Settings"]