---
sidebar_position: 1
---

# Fundação HTTP

Fonte de verdade: [`ADR 0001`](https://github.com/Vintex-Ages/back-end/blob/develop/.ai/adr/0001-fundacao-http-kit-api.md). Esta página resume as decisões para quem está lendo a documentação, não o histórico da decisão.

## Prefixo de rota

Todas as rotas ficam sob `/api`, sem `/v1` (não existe uma segunda versão da API ainda).

## Envelope de erro

Toda resposta de erro segue:

```json
{
  "error": {
    "code": "STRING_CONSTANTE",
    "message": "texto pt-BR",
    "fields": { "campo": "motivo" }
  }
}
```

- `code` vem de `app/core/errors.py::ErrorCode`.
- `fields` só aparece em `422` (erro de validação).
- Controllers e repositories levantam `AppError`/`NotFound`/`Conflict`/`Unauthorized`/`Forbidden`/`ValidationError` — a rota nunca monta `HTTPException` nem decide o status.

## Autorização por papel

Fonte de verdade: [`ADR 0002`](https://github.com/Vintex-Ages/back-end/blob/develop/.ai/adr/0002-autenticacao-jwt.md) e `app/core/security.py`. O acesso a funções é autorizado por papel em todas as rotas (RN-32).

| Dependency | Quem passa | Sem sessão | Sem o papel |
| --- | --- | --- | --- |
| `require_auth` / `get_current_user` | qualquer usuário logado | `401 AUTH_REQUIRED` | — |
| `require_seller` | quem tem linha em `sellers` | `401 AUTH_REQUIRED` | `403 FORBIDDEN` |
| `require_admin` | `users.is_admin` | `401 AUTH_REQUIRED` | `403 ADMIN_REQUIRED` |
| `optional_user` | todo mundo; devolve `None` para visitante | — | — |

- **O papel vem do banco, nunca da claim do token.** O `is_admin` do JWT é informativo: um token emitido antes de o papel ser retirado não continua valendo como admin.
- **Rotas de administração ficam em `app/views/admin_routes.py`, sob `/api/admin`, com a guarda no próprio router.** Rota nova ali nasce exigindo o papel; esquecer o `Depends` não abre a rota. `tests/test_admin_guard.py` confere no app real que toda rota sob `/api/admin` responde 401 sem sessão e 403 para comprador.
- **`ADMIN_REQUIRED` é código próprio**, e não o `FORBIDDEN` genérico, para o front distinguir "sem papel de administradora" de "sem acesso a este recurso" ([#61](https://github.com/Vintex-Ages/back-end/issues/61)).

A conta da administradora vem do seed (`python -m app.seeds.admin`): ver a seção *Conta da administradora* do README. Em produção a senha vem de `SEED_ADMIN_PASSWORD`, e o seed recusa rodar sem ela.

## Paginação

- `page` (≥ 1, default 1) e `page_size` (1–100, default 20) como query params.
- Resposta: `{ "items": [...], "page", "page_size", "total" }`.
- Uma consulta de dados + uma de contagem, nunca uma por linha.

## Fronteira de transação

`get_db` só cede e fecha a sessão. O **controller** chama `db.commit()` no sucesso; repositories não commitam.

## CORS

`settings.CORS_ORIGINS` (env `CORS_ORIGINS`), default `*`. Em produção, lista separada por vírgula — o código não muda entre ambientes.
