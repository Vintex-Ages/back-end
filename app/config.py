from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vintex"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_PORT: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()
