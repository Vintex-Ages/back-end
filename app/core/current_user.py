"""Identidade do usuário logado — placeholder até a autenticação (#151) mergear.

Nenhuma rota fica esperando a autenticação: quem chama recebe o id via
header `X-User-Id` e usa `Depends(get_current_user_id)`. Quando a #151
entrar, a troca é o corpo desta função, em um arquivo só.
"""

from fastapi import Header


def get_current_user_id(x_user_id: int | None = Header(default=None)) -> int:
    return x_user_id or 1  # usuário do seed
