from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

_INSECURE_JWT_SECRET = "dev-only-change-me"


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
    JWT_SECRET: str = _INSECURE_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Conta da administradora criada por `python -m app.seeds.admin`
    # (back-end#61). Vazio em desenvolvimento usa a senha documentada no
    # README; em produção o seed recusa rodar sem ela. O domínio é o
    # `example.com` (RFC 2606) e não o `.local` das contas de `lojas.py`: o
    # `EmailStr` do login recusa `.local`, e esta conta precisa entrar.
    SEED_ADMIN_EMAIL: str = "admin@vintex.example.com"
    SEED_ADMIN_PASSWORD: str = ""
    # Provedor de IA ativo (chave registrada em app/services/ai/factory.py).
    # Nenhum fornecedor foi escolhido ainda (ver .ai/architecture.md); o
    # padrão "unavailable" degrada sem erro fatal (VE-06).
    AI_PROVIDER: str = "unavailable"

    # Cota da busca conversacional (back-end#258), por dia UTC. O provedor
    # gratuito dá 50 requisições por dia para o projeto inteiro, e a mesma
    # chave serve a sugestão de anúncio pela foto e o vetor da peça publicada:
    # 40 para o chat deixa margem a eles. Pessoa logada conta pelo id;
    # visitante, pela origem da requisição.
    CHAT_QUOTA_PER_PERSON: int = Field(default=5, ge=1)
    CHAT_QUOTA_PER_DAY: int = Field(default=40, ge=1)

    # Sugestão de preço (back-end#254): abaixo de tantas peças parecidas no
    # catálogo, a faixa vem nula em vez de um número sem base.
    PRICE_SUGGESTION_MIN_BASE: int = Field(default=3, ge=1)

    # Embedding do catálogo (BE-US027-1, back-end#92). Só lido quando
    # AI_PROVIDER=google; a chave vem do Google AI Studio (camada gratuita).
    GOOGLE_API_KEY: str = ""
    GOOGLE_EMBEDDING_MODEL: str = "gemini-embedding-2"
    # Preenchimento automático da peça a partir da foto (back-end#150) —
    # modelo multimodal (lê imagem), diferente do de embedding.
    #
    # Aceita vários nomes separados por vírgula (back-end#209): um 503 no
    # primeiro faz tentar o próximo. A capacidade do provedor oscila por
    # modelo — medido em 27/09, 4 falhas em 5 chamadas num intervalo de vinte
    # minutos, com seis outros modelos respondendo no mesmo período.
    GOOGLE_VISION_MODEL: str = "gemini-3.1-flash-lite,gemini-3.8-flash,gemini-3.7-flash"

    # VE-18 (#169): configuração do produtor/worker de análise de imagens.
    AI_ANALYSIS_QUEUE_URL: str = ""
    SQS_ENDPOINT_URL: str | None = None
    AI_WORKER_PROVIDER: str = "unavailable"
    FREELLMAPI_BASE_URL: str = "http://freellmapi:3001/v1"
    FREELLMAPI_API_KEY: str = ""
    FREELLMAPI_MODEL: str = "auto"

    # Storage de mídia (VE-16). Sem endpoint explícito, boto3 usa a AWS.
    # Base publica da propria API, usada para montar a URL da midia. Fica
    # configuravel porque a URL precisa ser alcancavel pelo servidor: e ele
    # que baixa a foto para mandar ao modelo multimodal. Vazio usa a base da
    # requisicao, que serve para desenvolvimento.
    PUBLIC_BASE_URL: str = ""
    # Só para downloads no servidor; nunca altera URLs devolvidas ao navegador.
    MEDIA_INTERNAL_BASE_URL: str = ""

    AWS_REGION: str = "us-east-2"
    S3_ENDPOINT_URL: str | None = None
    MEDIA_BUCKET: str | None = None

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> list[str]:
        value = self.CORS_ORIGINS.strip()
        if value in ("", "*"):
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _recusa_segredo_padrao_em_producao(self) -> "Settings":
        if self.APP_ENV == "production" and self.JWT_SECRET == _INSECURE_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET não pode ser o valor padrão de desenvolvimento "
                "quando APP_ENV=production. Configure um segredo forte e "
                "único no ambiente de deploy."
            )
        return self


settings = Settings()
