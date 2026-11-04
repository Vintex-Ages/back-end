"""Adaptador de análise de imagens para o endpoint interno FreeLLMAPI."""

from __future__ import annotations

import base64
from collections.abc import Sequence

import httpx

from app.config import settings
from app.services.ai.analysis_prompt import ANALYZE_IMAGE_PROMPT
from app.services.ai.base import (
    AIProviderError,
    AIProviderUnavailableError,
    ImageAnalysisProvider,
    ImageAnalysisResult,
)
from app.services.ai.media_urls import image_download_url

_IMAGE_TIMEOUT_SECONDS = 10.0
_PROVIDER_TIMEOUT_SECONDS = 45.0
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 24 * 1024 * 1024
_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VintexBot/1.0)"}


class FreeLLMAPIProvider(ImageAnalysisProvider):
    """Gera sugestões de cadastro usando o endpoint OpenAI compatível interno."""

    def __init__(self) -> None:
        if not settings.FREELLMAPI_API_KEY:
            raise AIProviderUnavailableError(
                "FREELLMAPI_API_KEY não configurada para o worker de IA."
            )
        self._base_url = settings.FREELLMAPI_BASE_URL.rstrip("/")
        self._api_key = settings.FREELLMAPI_API_KEY
        self._model = settings.FREELLMAPI_MODEL

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        if not image_urls:
            return ImageAnalysisResult()

        images = self._download_images(image_urls)
        content: list[dict[str, object]] = [
            {"type": "text", "text": ANALYZE_IMAGE_PROMPT}
        ]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
            for data_url in images
        )

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": content}],
                    "response_format": {"type": "json_object"},
                },
                timeout=_PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("resposta vazia")
            return ImageAnalysisResult.model_validate_json(answer)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError(
                "FreeLLMAPI falhou ou devolveu uma análise inválida."
            ) from exc

    @staticmethod
    def _download_images(image_urls: Sequence[str]) -> list[str]:
        total_bytes = 0
        data_urls: list[str] = []
        try:
            with httpx.Client(
                timeout=_IMAGE_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers=_DOWNLOAD_HEADERS,
            ) as client:
                for url in image_urls:
                    with client.stream("GET", image_download_url(url)) as response:
                        response.raise_for_status()
                        media_type = response.headers.get("content-type", "").split(
                            ";", maxsplit=1
                        )[0]
                        if media_type not in _ALLOWED_CONTENT_TYPES:
                            raise AIProviderError(
                                "Tipo de arquivo não suportado para a foto."
                            )

                        image = bytearray()
                        for chunk in response.iter_bytes(_DOWNLOAD_CHUNK_SIZE):
                            image.extend(chunk)
                            total_bytes += len(chunk)
                            if len(image) > _MAX_IMAGE_BYTES:
                                raise AIProviderError(
                                    "Foto excede o tamanho máximo de 8 MiB."
                                )
                            if total_bytes > _MAX_TOTAL_BYTES:
                                raise AIProviderError(
                                    "Fotos somadas excedem o tamanho máximo de 24 MiB."
                                )

                    encoded = base64.b64encode(image).decode("ascii")
                    data_urls.append(f"data:{media_type};base64,{encoded}")
        except httpx.HTTPError:
            # Evita incluir a URL, que pode conter query string pré-assinada.
            raise AIProviderError("Falha ao baixar foto da peça.") from None
        return data_urls
