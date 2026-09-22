# Ver app/config.py — recusa o JWT_SECRET padrão de dev quando APP_ENV=production.

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_producao_com_segredo_padrao_de_dev_recusa_subir():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="dev-only-change-me",
            DATABASE_URL="sqlite://",
        )


def test_producao_com_segredo_proprio_sobe_normalmente():
    settings = Settings(
        APP_ENV="production",
        JWT_SECRET="um-segredo-forte-gerado-so-para-producao",
        DATABASE_URL="sqlite://",
    )
    assert settings.JWT_SECRET == "um-segredo-forte-gerado-so-para-producao"


def test_desenvolvimento_com_segredo_padrao_sobe_normalmente():
    settings = Settings(APP_ENV="development", DATABASE_URL="sqlite://")
    assert settings.JWT_SECRET == "dev-only-change-me"
