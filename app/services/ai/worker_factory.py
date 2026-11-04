"""Seleção do provider usado exclusivamente pelo worker de imagens."""

from app.config import settings
from app.services.ai.base import ImageAnalysisProvider
from app.services.ai.freellmapi import FreeLLMAPIProvider
from app.services.ai.unavailable import UnavailableAIProvider


def get_image_analysis_provider() -> ImageAnalysisProvider:
    if settings.AI_WORKER_PROVIDER == "freellmapi":
        return FreeLLMAPIProvider()
    return UnavailableAIProvider()
