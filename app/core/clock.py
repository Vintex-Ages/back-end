"""Relógio compartilhado — datetime UTC sem tzinfo.

`BaseModel` usa `func.now()` (server-side) para `created_at`/`updated_at`,
sempre naive. Qualquer datetime calculado em Python (expiração e revogação
de refresh token) precisa ser naive-UTC pra comparar de forma consistente
com o que vem do banco. Um único ponto evita que cada lugar recalcule
`datetime.now(timezone.utc).replace(tzinfo=None)` por conta própria.
"""

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
