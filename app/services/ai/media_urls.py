"""Resolução de mídia própria para downloads dentro da rede de contêineres."""

from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from app.config import settings


def image_download_url(url: str) -> str:
    """Troca somente a origem pública configurada de `/api/media/`.

    URLs de terceiros e URLs públicas devolvidas pela API permanecem intactas.
    Sem ambas as configurações, preserva o comportamento existente.
    """
    if not settings.PUBLIC_BASE_URL or not settings.MEDIA_INTERNAL_BASE_URL:
        return url
    try:
        source = urlsplit(url)
        public = urlsplit(settings.PUBLIC_BASE_URL)
        internal = urlsplit(settings.MEDIA_INTERNAL_BASE_URL)
        if any(
            part.scheme not in {"http", "https"}
            or not part.hostname
            or part.username is not None
            or part.password is not None
            for part in (source, public, internal)
        ):
            return url

        def origin(part: SplitResult) -> tuple[str, str | None, int]:
            return (
                part.scheme,
                part.hostname,
                part.port or (443 if part.scheme == "https" else 80),
            )

        if origin(source) != origin(public):
            return url
        if any(
            part.path not in {"", "/"} or part.query or part.fragment
            for part in (public, internal)
        ):
            return url
        decoded = unquote(source.path)
        if (
            not decoded.startswith("/api/media/")
            or any(segment in {".", ".."} for segment in decoded.split("/"))
            or "\\" in decoded
        ):
            return url
        return urlunsplit(
            (internal.scheme, internal.netloc, source.path, source.query, "")
        )
    except ValueError:
        return url
