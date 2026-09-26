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

## Paginação

- `page` (≥ 1, default 1) e `page_size` (1–100, default 20) como query params.
- Resposta: `{ "items": [...], "page", "page_size", "total" }`.
- Uma consulta de dados + uma de contagem, nunca uma por linha.

## Fronteira de transação

`get_db` só cede e fecha a sessão. O **controller** chama `db.commit()` no sucesso; repositories não commitam.

## CORS

`settings.CORS_ORIGINS` (env `CORS_ORIGINS`), default `*`. Em produção, lista separada por vírgula — o código não muda entre ambientes.
