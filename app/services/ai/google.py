"""Provedor real do Google AI Studio (BE-US027-1, back-end#92).

Primeira chamada real a uma API de IA no projeto — até aqui, `unavailable`
era o único provider (VE-06). Cobre `embed` e `analyze_image`;
`stream_interpret_search` (VS-027, geração de texto conversacional) ainda
não tem implementação real, então degrada como `UnavailableAIProvider` em
vez de fingir suportar algo que não foi escrito.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

import httpx
from google import genai
from google.genai import types

from app.config import settings
from app.constants.catalog import CATEGORIES, COLORS, CONDITIONS, SIZES, lista
from app.constants.embedding import EMBEDDING_DIM
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
    ChatTurn,
    ImageAnalysisResult,
    SearchStreamEvent,
)

_NOT_IMPLEMENTED = (
    "GoogleAIProvider ainda não implementa este método (fora do escopo do back-end#92)."
)

# Os quatro campos de lista fechada citam o vocabulário do catálogo
# (`app/constants/catalog.py`). Sem isso o modelo responde texto livre —
# "Camiseta" para categoria, "Branco e preto" para cor — e o formulário
# descarta, porque nenhum dos dois existe nas opções da tela. Dar a lista
# muda o preenchimento de 2 campos para 5.
_ANALYZE_IMAGE_PROMPT = f"""\
Você está ajudando um vendedor de brechó a cadastrar uma peça de roupa a \
partir das fotos dela. Analise as imagens e sugira, em português:

- category: escolha UM valor exato desta lista: {lista(CATEGORIES)}. \
É a família da peça no catálogo, não o tipo dela: uma camiseta é "Roupas", \
um tênis é "Sapatos", uma bolsa é "Acessórios".
- color: escolha UM valor exato desta lista: {lista(COLORS)}. \
Se a peça tiver mais de uma cor, escolha a predominante; use "Estampado" \
quando não houver uma cor dominante.
- size: escolha UM valor exato desta lista: {lista(SIZES)}, e só se o \
tamanho estiver legível numa etiqueta na foto. Não estime pelo caimento.
- condition: escolha UM valor exato desta lista: {lista(CONDITIONS)}.
- description: uma frase curta descrevendo a peça. Texto livre.
- brand: a marca, APENAS se houver uma etiqueta ou logo legível na foto — \
se não houver etiqueta visível ou não for possível ler com certeza, não \
preencha este campo. Nunca chute a marca a partir do estilo da peça.

Nos quatro campos de lista, responda com o valor exato como está escrito \
acima, com acento e maiúscula. Se nenhum valor da lista servir, deixe o \
campo nulo — é melhor vazio que aproximado, porque o vendedor corrige um \
campo vazio mas não percebe um valor errado.

Para cada campo que conseguir sugerir, dê um `value` e uma `confidence` \
(0 a 1) de quão certo você está. Deixe o campo nulo se não conseguir \
sugerir algo com razoável confiança — melhor um campo vazio que um chute.
"""

# Teto para a chamada ao modelo (o SDK conta em milissegundos).
_GOOGLE_TIMEOUT_MS = 30_000


def _lista(valor: str) -> list[str]:
    nomes = [n.strip() for n in valor.split(",")]
    return [n for n in nomes if n]


def modelos_de_visao() -> list[str]:
    """`GOOGLE_VISION_MODEL` como lista, aceitando um nome só ou vários
    separados por vírgula."""
    return _lista(settings.GOOGLE_VISION_MODEL)


# Não existe `modelos_de_embedding()`, e é decisão, não esquecimento.
#
# O primeiro critério da `#209` pedia lista de modelos para visão **e** para
# embedding. O `#224` implementou o de embedding e foi revertido no `#227`,
# porque o critério estava errado quando eu o escrevi:
#
#   1. `find_similar` não filtra por `embedding_model`. Se o fallback
#      disparasse, o vetor da pergunta viria de um modelo e os do catálogo de
#      outro — e distância entre espaços vetoriais diferentes é ruído
#      apresentado como resultado. Um 503 é melhor: falha alto, o front mostra
#      "indisponível", e ninguém recebe resposta errada com cara de certa.
#   2. `scripts/backfill_embeddings.py` lê `GOOGLE_EMBEDDING_MODEL` cru para
#      gravar em `Product.embedding_model` (`String(60)`) e para decidir o que
#      reprocessar. Com lista, gravaria a lista inteira e reprocessaria o
#      catálogo a cada mudança de ordem.
#
# Fallback de visão é diferente e continua: cada `analyze_image` é
# independente, não há vetor guardado com que o resultado precise ser
# comparável.
#
# Tornar isto seguro é a `#231`: `find_similar` filtrar pelo modelo que gerou
# cada vetor, e o backfill usar um nome só. A `#228`, que carregava isto, foi
# agrupada lá — é a mesma consulta e o mesmo arquivo.


def _e_indisponibilidade(exc: Exception) -> bool:
    """503 do provedor, pelo código do SDK ou pela mensagem."""
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if codigo == 503:
        return True
    return "503" in str(exc) and "UNAVAILABLE" in str(exc).upper()


logger = logging.getLogger(__name__)

_IMAGE_DOWNLOAD_TIMEOUT_S = 10.0
# Alguns hosts (ex.: Wikimedia) recusam requisições sem User-Agent de navegador.
_IMAGE_DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VintexBot/1.0)"}

# Sem isso, uma foto (ou uma lista delas) arbitrariamente grande é baixada
# inteira em memória antes de qualquer verificação (revisão da Adrielle no
# PR #200). A quantidade de fotos já é limitada no schema da requisição
# (`ListingSuggestionsRequest`); aqui é o tamanho de cada uma.
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB por foto
_MAX_TOTAL_BYTES = 24 * 1024 * 1024  # 24 MiB somando todas as fotos da chamada
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_DOWNLOAD_CHUNK_SIZE = 64 * 1024


class GoogleAIProvider(AIProvider):
    def __init__(self) -> None:
        if not settings.GOOGLE_API_KEY:
            raise AIProviderUnavailableError(
                "GOOGLE_API_KEY não configurada para AI_PROVIDER=google."
            )
        # Sem `timeout`, o SDK passa `timeout=None` ao httpx, que significa
        # esperar para sempre. A rota e sincrona: uma chamada pendurada segura
        # uma thread do pool, e algumas delas derrubam a API inteira. A regra
        # da #150 e que demora tambem nao pode travar o cadastro.
        self._client = genai.Client(
            api_key=settings.GOOGLE_API_KEY,
            http_options=types.HttpOptions(timeout=_GOOGLE_TIMEOUT_MS),
        )

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        if not image_urls:
            return ImageAnalysisResult()

        parts = [types.Part.from_text(text=_ANALYZE_IMAGE_PROMPT)]
        total_bytes = 0
        try:
            with httpx.Client(
                timeout=_IMAGE_DOWNLOAD_TIMEOUT_S,
                follow_redirects=True,
                headers=_IMAGE_DOWNLOAD_HEADERS,
            ) as client:
                for url in image_urls:
                    with client.stream("GET", url) as photo:
                        photo.raise_for_status()
                        mime_type = photo.headers.get("content-type", "").split(";")[0]
                        if mime_type not in _ALLOWED_CONTENT_TYPES:
                            raise AIProviderError(
                                f"Tipo de arquivo não suportado para a foto: {mime_type or 'desconhecido'!r}."
                            )

                        chunks = bytearray()
                        for chunk in photo.iter_bytes(_DOWNLOAD_CHUNK_SIZE):
                            chunks += chunk
                            total_bytes += len(chunk)
                            if len(chunks) > _MAX_IMAGE_BYTES:
                                raise AIProviderError(
                                    f"Foto excede o tamanho máximo de {_MAX_IMAGE_BYTES // (1024 * 1024)}MiB."
                                )
                            if total_bytes > _MAX_TOTAL_BYTES:
                                raise AIProviderError(
                                    f"Fotos somadas excedem o tamanho máximo de {_MAX_TOTAL_BYTES // (1024 * 1024)}MiB."
                                )

                    parts.append(
                        types.Part.from_bytes(data=bytes(chunks), mime_type=mime_type)
                    )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Falha ao baixar foto da peça: {exc}") from exc

        result = self._gerar_com_fallback(parts)

        parsed = result.parsed
        if isinstance(parsed, ImageAnalysisResult):
            return parsed
        if result.text:
            try:
                return ImageAnalysisResult.model_validate_json(result.text)
            except ValueError as exc:
                raise AIProviderError(
                    f"Resposta do provedor não bate com o formato esperado: {exc}"
                ) from exc
        raise AIProviderError("Provedor não devolveu uma análise para as fotos.")

    async def stream_interpret_search(
        self, query: str, history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[SearchStreamEvent]:
        raise AIProviderUnavailableError(_NOT_IMPLEMENTED)
        yield  # pragma: no cover - nunca alcançado; mantém a função geradora

    def _gerar_com_fallback(
        self, parts: list[types.Part]
    ) -> types.GenerateContentResponse:
        """Tenta os modelos configurados em ordem, pulando os que dão 503.

        Só o 503 faz seguir para o próximo: é falta de capacidade do provedor,
        e outro modelo costuma estar de pé no mesmo instante. 404 (nome que
        não existe para a chave) e 400 (entrada recusada) são erro nosso, e
        tentar outro só esconderia a causa.
        """
        modelos = modelos_de_visao()
        if not modelos:
            # Sem isto, lista vazia caía no `raise` do fim com `ultimo = None` e
            # produzia "Falha ao analisar as fotos: None", que não diz nada.
            raise AIProviderError(
                "GOOGLE_VISION_MODEL está vazio: nenhum modelo para tentar."
            )
        ultimo: Exception | None = None

        for indice, modelo in enumerate(modelos):
            try:
                return self._client.models.generate_content(
                    model=modelo,
                    contents=[types.Content(parts=parts)],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ImageAnalysisResult,
                    ),
                )
            except Exception as exc:  # SDK do Google não documenta uma exceção só
                ultimo = exc
                if not _e_indisponibilidade(exc) or indice == len(modelos) - 1:
                    raise AIProviderError(f"Falha ao analisar as fotos: {exc}") from exc

                logger.warning(
                    "Modelo %s indisponível (503); tentando %s",
                    modelo,
                    modelos[indice + 1],
                )

        raise AIProviderError(f"Falha ao analisar as fotos: {ultimo}")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        # Um `types.Content` por texto: `contents=list(texts)` (strings soltas)
        # faz o SDK tratar a lista inteira como as partes de UM conteúdo só,
        # devolvendo um único vetor para todos os textos juntos — não um por
        # texto. Encapsular cada texto no seu próprio `Content` é o que faz o
        # batch devolver um vetor por entrada, na mesma ordem.
        contents = [types.Content(parts=[types.Part(text=text)]) for text in texts]
        # Um nome de modelo só, de propósito — o bloco de comentário no topo
        # deste arquivo explica por que não há fallback aqui.
        try:
            response = self._client.models.embed_content(
                model=settings.GOOGLE_EMBEDDING_MODEL,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
            )
        except Exception as exc:  # SDK do Google não documenta uma exceção só
            raise AIProviderError(f"Falha ao gerar embedding: {exc}") from exc

        if response.embeddings is None or len(response.embeddings) != len(texts):
            raise AIProviderError(
                "Resposta de embedding do Google não tem um vetor por texto enviado."
            )

        vectors = [list(item.values or []) for item in response.embeddings]
        if any(len(vector) != EMBEDDING_DIM for vector in vectors):
            # Sem isso, um vetor vazio (`values=None`) ou de dimensão errada
            # (ex.: o modelo trocou o padrão) é gravado como se fosse válido —
            # e como o backfill é idempotente por `embedding IS NOT NULL`, a
            # peça nunca mais seria reprocessada, mesmo com o provedor bom.
            raise AIProviderError(
                f"Provedor devolveu vetor com dimensão diferente de {EMBEDDING_DIM}."
            )
        return vectors
