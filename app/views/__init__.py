"""Agregador de routers da API.

Todo router de domínio entra sob o prefixo `/api` aqui. O `main.py` inclui
apenas `api_router`.

    from app.views.products import router as products_router
    api_router.include_router(products_router)
"""

from fastapi import APIRouter

from app.views.legal_routes import router as legal_router
from app.views.product_routes import me_router as product_me_router
from app.views.product_routes import router as product_router
from app.views.style_routes import router as styles_router

api_router = APIRouter(prefix="/api")

# Routers de domínio (feed, auth, stores, styles...) são incluídos aqui
# conforme as issues de rota forem entregues.
api_router.include_router(product_router)
api_router.include_router(product_me_router)
api_router.include_router(styles_router)
api_router.include_router(legal_router)
