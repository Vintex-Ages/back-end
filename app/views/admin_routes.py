"""Rotas da administradora (back-end#61).

A guarda fica no router, e não em cada rota: toda rota que entrar aqui (a fila
de comprovantes da #250, aprovar e rejeitar da #251) nasce exigindo o papel.
Esquecer o `Depends` numa rota nova não abre a rota (RN-32).
"""

from fastapi import APIRouter, Depends

from app.core.security import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
