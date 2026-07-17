from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # To support .env
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # The names here must match with the names from .env file. Names here are in lower case and in .env file they are in Upper case.
    database_url: str
    api_key: str
    embedding_dim: int


# First time calling this will create the settings instance. All the other call coming after it, will get the cached instance.
@lru_cache(maxsize=1)
def get_settings():
    settings = Settings()
    return settings


# print(Settings().model_dump(by_alias=True))
