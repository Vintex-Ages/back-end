"""Cada router entra uma vez so no agregador (back-end#141).

A resolucao do conflito entre a loja publica (#142) e a loja do vendedor
(#141) uniu os dois lados por uniao e repetiu `store_router` e
`store_me_router` no `app/views/__init__.py`. O roteamento continuava certo
-- as duas inclusoes eram identicas, e a primeira vence -- e o schema
servido tambem, porque o FastAPI deduplica na geracao. O que sobrava eram
quatro `UserWarning: Duplicate Operation ID` por geracao de OpenAPI, ou
seja, a cada `/docs` e a cada suite de teste.

Custo real: o canal de aviso vira ruido e para de servir de sinal quando
alguem duplicar de verdade. E por isso que o teste olha o aviso, e nao o
schema -- o schema nunca acusou nada.

Este teste usa so API publica (`app.openapi()`). A tentativa de contar pares
(metodo, caminho) em `api_router.routes` nao serve: nesta versao do FastAPI
`include_router` guarda um `_IncludedRouter` e nao achata as rotas, entao a
contagem dava zero com o defeito presente.
"""

from __future__ import annotations

import warnings

from app.main import create_app


def test_gerar_o_openapi_nao_emite_aviso_de_operation_id_duplicado() -> None:
    app = create_app()

    with warnings.catch_warnings(record=True) as capturados:
        warnings.simplefilter("always")
        app.openapi()

    duplicados = [
        str(a.message) for a in capturados if "Duplicate Operation ID" in str(a.message)
    ]

    assert (
        duplicados == []
    ), f"{len(duplicados)} router(s) incluido(s) duas vezes: {duplicados}"
