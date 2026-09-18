from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vintex"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_PORT: int = 8000

    # Origens permitidas para CORS. "*" libera todas (uso em dev);
    # em produção, informe a lista separada por vírgula.
    CORS_ORIGINS: str = "*"

    # Provedor de IA ativo (chave registrada em app/services/ai/factory.py).
    # Nenhum fornecedor foi escolhido ainda (ver .ai/architecture.md); o
    # padrão "unavailable" degrada sem erro fatal (VE-06).
    AI_PROVIDER: str = "unavailable"

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> list[str]:
        value = self.CORS_ORIGINS.strip()
        if value in ("", "*"):
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]


settings = Settings()
