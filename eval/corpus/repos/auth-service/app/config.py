from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://auth:auth@localhost/auth"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    login_attempts_per_minute: int = 5


settings = Settings()
