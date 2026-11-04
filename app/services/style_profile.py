"""O perfil de estilo da pessoa como vetor de consulta (back-end#253).

O onboarding grava os estilos escolhidos em `user_preferences` (tipo
`estilo`). A recomendação compara esse perfil com o vetor das peças, por
similaridade (RN-62, RN-64): o perfil vira um texto, e o texto vira vetor pelo
mesmo modelo que gerou o vetor das peças.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.constants.styles import STYLES
from app.models.user_preference import UserPreference
from app.services.ai import AIProviderError, get_ai_provider, modelo_de_embedding

TIPO_ESTILO = "estilo"

_ESTILOS = {estilo["value"]: estilo for estilo in STYLES}


def texto_do_perfil(preferencias: Sequence[UserPreference]) -> str | None:
    """O texto dos estilos escolhidos, ou `None` sem estilo nenhum.

    Para cada estilo, o identificador, o rótulo e a descrição do catálogo de
    estilos. As peças guardam o estilo pelo mesmo identificador (`style`), e
    ele entra no texto do vetor delas: o perfil fala a mesma língua.
    """
    partes: list[str] = []
    for preferencia in preferencias:
        if preferencia.type != TIPO_ESTILO:
            continue
        estilo = _ESTILOS.get(preferencia.value)
        if estilo is None:
            partes.append(preferencia.value)
        else:
            partes.append(
                f"{estilo['value']} {estilo['label']} {estilo['description']}"
            )
    return " ".join(partes) or None


def vetor_do_perfil(texto: str) -> tuple[list[float], str]:
    """O vetor do perfil e o modelo que o gerou.

    A home pede a recomendação a cada carregamento: o vetor de cada texto de
    perfil fica em memória, e o mesmo perfil não chama a IA de novo. Mudar o
    perfil muda o texto, e o texto novo gera outro vetor. Falha não fica em
    cache.
    """
    modelo = modelo_de_embedding()
    return list(_vetor_em_cache(texto, modelo)), modelo


@lru_cache(maxsize=128)
def _vetor_em_cache(texto: str, modelo: str) -> tuple[float, ...]:
    vetores = get_ai_provider().embed([texto])
    if len(vetores) != 1:
        raise AIProviderError(
            f"O provedor devolveu {len(vetores)} vetores para 1 texto."
        )
    return tuple(vetores[0])


def limpar_cache() -> None:
    """Esquece os vetores de perfil guardados (usado pelos testes)."""
    _vetor_em_cache.cache_clear()
