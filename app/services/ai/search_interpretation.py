"""Da pergunta em linguagem natural ao filtro do catálogo (back-end#260).

A pergunta do chat tem duas partes. O que é objetivo (categoria, preço,
tamanho, cor, marca, conservação) **corta** o resultado, em SQL. O que é
subjetivo (estilo, ocasião, descrição) **ordena**, por similaridade. Antes,
tudo era similaridade: "tênis verde até 400" devolvia o mais parecido no
espaço vetorial, e um tênis branco de outro preço podia vir primeiro.

O modelo de IA só **lê** a pergunta. Quem decide o que entra como filtro é
este módulo, contra o vocabulário fechado do catálogo
(`app/constants/catalog.py`): um valor que não existe na lista não vira
filtro, porque cortaria o catálogo inteiro por um valor que nenhuma peça tem.

Independe do fornecedor: cada provider monta a chamada do seu jeito e passa a
resposta por `interpretacao_da_resposta`.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.constants.catalog import CATEGORIES, COLORS, CONDITIONS, SIZES, lista
from app.services.ai.base import ChatTurn, InterpretedQuery

# Turnos anteriores que vão junto: o bastante para "e em azul?" saber do que
# se fala, sem mandar a conversa inteira a cada pergunta.
_TURNOS_DE_CONTEXTO = 6
_CARACTERES_POR_TURNO = 500


class InterpretacaoDaPergunta(BaseModel):
    """O formato pedido ao modelo. Tudo opcional: pergunta sem atributo
    objetivo é a regra, não a exceção."""

    category: str | None = None
    color: str | None = None
    size: str | None = None
    condition: str | None = None
    brand: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    similarity: str | None = None


INTERPRET_SEARCH_PROMPT = f"""\
Você interpreta perguntas feitas à Vintex, a assistente de um marketplace de \
brechós. Não responda à pergunta nem sugira peças: só separe o que ela pede.

Campos objetivos (preencha só o que a pessoa pediu com clareza):
- category: UM valor exato desta lista: {lista(CATEGORIES)}. É a família da \
peça, não o tipo: vestido, calça e camiseta são "Roupas"; tênis, bota e \
sandália são "Sapatos"; bolsa, cinto e óculos são "Acessórios".
- color: UM valor exato desta lista: {lista(COLORS)}.
- size: UM valor exato desta lista: {lista(SIZES)}.
- condition: UM valor exato desta lista: {lista(CONDITIONS)}.
- brand: a marca, só se a pessoa disser o nome dela.
- price_min e price_max: em reais, só com número dito. "até 400" é \
price_max 400; "a partir de 100" é price_min 100; "entre 100 e 200" são os dois.

similarity: o que sobra e é subjetivo — estilo, ocasião, uso, caimento, \
descrição ("para festa", "de corrida masculino", "estilo boho"). Sem repetir \
o que já foi para os campos objetivos. Nulo se não sobrar nada.

Nos campos de lista, use o valor exato como está escrito acima, com acento e \
maiúscula. Se nenhum valor servir, deixe nulo: é melhor sem filtro que com o \
filtro errado. Use a conversa anterior só para entender a pergunta atual \
("e em azul?" mantém o resto do que foi pedido antes).
"""


def montar_pergunta(query: str, history: Sequence[ChatTurn] = ()) -> str:
    """O texto que vai ao modelo depois do prompt: a conversa recente e a
    pergunta, cada mensagem cortada num tamanho fixo."""
    linhas = []
    recentes = list(history)[-_TURNOS_DE_CONTEXTO:]
    if recentes:
        linhas.append("Conversa anterior:")
        for turno in recentes:
            quem = "Pessoa" if turno.role == "user" else "Vintex"
            linhas.append(f"{quem}: {turno.text[:_CARACTERES_POR_TURNO]}")
        linhas.append("")
    linhas.append(f"Pergunta atual: {query[:_CARACTERES_POR_TURNO]}")
    return "\n".join(linhas)


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _da_lista(valor: str | None, valores: tuple[str, ...]) -> str | None:
    """O valor como o catálogo grava, ou `None` se não estiver na lista.

    Aceita caixa e acento diferentes ("verde", "Acessorios"), que os filtros
    também ignoram; não aceita sinônimo nem aproximação.
    """
    if not valor:
        return None
    alvo = _sem_acento(valor)
    return next((v for v in valores if _sem_acento(v) == alvo), None)


def _preco(valor: float | None) -> Decimal | None:
    if valor is None:
        return None
    try:
        preco = Decimal(str(valor))
    except InvalidOperation:
        return None
    # `NaN` e `Infinity` passam pelo `float` do schema. Comparar `NaN` levanta
    # `InvalidOperation`, que não é erro de provedor e derrubaria o chat.
    if not preco.is_finite() or preco < 0:
        return None
    return preco


def _texto_do_preco(preco: Decimal) -> str:
    """`400`, e não `400.0`: é o que o front mostra no chip."""
    return format(preco.normalize(), "f")


def interpretacao_da_resposta(dados: InterpretacaoDaPergunta) -> InterpretedQuery:
    """A resposta do modelo, só com o que pode virar filtro do catálogo.

    `filters` usa os nomes dos filtros do feed (`category`, `price_max`...),
    para o controller montar `ProductFilters` direto deles.
    """
    filtros: dict[str, str] = {}
    for campo, valores in (
        ("category", CATEGORIES),
        ("color", COLORS),
        ("size", SIZES),
        ("condition", CONDITIONS),
    ):
        canonico = _da_lista(getattr(dados, campo), valores)
        if canonico:
            filtros[campo] = canonico

    if dados.brand and dados.brand.strip():
        filtros["brand"] = dados.brand.strip()

    minimo, maximo = _preco(dados.price_min), _preco(dados.price_max)
    # Faixa invertida é leitura errada, não pedido: nenhuma peça caberia nela.
    if minimo is not None and maximo is not None and minimo > maximo:
        minimo = maximo = None
    if minimo is not None:
        filtros["price_min"] = _texto_do_preco(minimo)
    if maximo is not None:
        filtros["price_max"] = _texto_do_preco(maximo)

    similarity = (dados.similarity or "").strip() or None
    return InterpretedQuery(filters=filtros, similarity=similarity)
