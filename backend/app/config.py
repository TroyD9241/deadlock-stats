from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://user:pass@localhost:5432/deadlock_stats"
    redis_url: str = "rediss://default:pass@redis.upstash.io:12345"
    secret_key: str = "dev-secret-change-in-prod"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 60

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
