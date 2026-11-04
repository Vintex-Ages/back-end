"""URLs públicas e internas mantêm contratos distintos (#169)."""

import pytest

from app.services.ai.media_urls import image_download_url, settings


@pytest.fixture
def internal_media(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://localhost:8080")
    monkeypatch.setattr(settings, "MEDIA_INTERNAL_BASE_URL", "http://api:8000")


def test_own_media_uses_internal_origin_without_changing_path(internal_media):
    assert (
        image_download_url(
            "http://localhost:8080/api/media/products/photos/a.jpg?version=1"
        )
        == "http://api:8000/api/media/products/photos/a.jpg?version=1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://external.test/api/media/a.jpg",
        "http://localhost:8081/api/media/a.jpg",
        "https://localhost:8080/api/media/a.jpg",
        "http://localhost:8080/api/users/me",
        "http://localhost:8080/api/media/../users/me",
        "http://localhost:8080/api/media/%2e%2e/users/me",
        "http://localhost:8080/api/media/%5cusers",
        "http://attacker@localhost:8080/api/media/a.jpg",
        "http://localhost:invalid/api/media/a.jpg",
        "/api/media/a.jpg",
    ],
)
def test_external_or_invalid_url_is_not_rewritten(internal_media, url):
    assert image_download_url(url) == url


@pytest.mark.parametrize("field", ["PUBLIC_BASE_URL", "MEDIA_INTERNAL_BASE_URL"])
def test_mapping_disabled_without_both_origins(internal_media, monkeypatch, field):
    monkeypatch.setattr(settings, field, "")
    url = "http://localhost:8080/api/media/a.jpg"
    assert image_download_url(url) == url


def test_default_port_and_host_case_refer_to_same_origin(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://Vintex.test")
    monkeypatch.setattr(settings, "MEDIA_INTERNAL_BASE_URL", "http://api:8000")
    assert image_download_url("https://vintex.test:443/api/media/a.jpg") == (
        "http://api:8000/api/media/a.jpg"
    )
