from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vintex"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_PORT: int = 8000

    # Origens permitidas para CORS. "*" libera todas (uso em dev);
    # em produção, informe a lista separada por vírgula.
    CORS_ORIGINS: str = "*"

    # Autenticação JWT — ver `.ai/adr/0002-autenticacao-jwt.md`.
    # Em produção, JWT_SECRET é obrigatório vir do ambiente (nunca este default).
    JWT_SECRET: str = "dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> list[str]:
        value = self.CORS_ORIGINS.strip()
        if value in ("", "*"):
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]


settings = Settings()
