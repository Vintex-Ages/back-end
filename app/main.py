from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.errors import register_exception_handlers
from app.views import api_router


def create_app() -> FastAPI:
    """Compõe a aplicação: middleware, handlers de erro e routers."""
    app = FastAPI(
        title="Vintex API",
        description="Backend da aplicação Vintex",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["infra"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
