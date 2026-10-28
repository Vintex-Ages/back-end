"""Identidade do usuário logado.

Toda rota que precisa saber quem é a pessoa depende de `get_current_user_id`.
Até a `#151` isto era um placeholder: lia o id de um cabeçalho `X-User-Id` e, na
falta dele, devolvia o usuário do seed. Ou seja, as rotas da Sprint 2 não tinham
autenticação nenhuma — aceitavam leitura e escrita sem token, e trocavam de
usuário por cabeçalho.

Agora resolve pela sessão real. Continua sendo um arquivo só, e nenhuma rota
mudou: era exatamente o que a `#151` declarava que seria.
"""

from fastapi import Depends

from app.core.security import get_current_user
from app.models.user import User


def get_current_user_id(user: User = Depends(get_current_user)) -> int:
    """Id do usuário autenticado. Sem token válido, `get_current_user` levanta 401."""
    return user.id
