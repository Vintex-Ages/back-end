# ADR 0001 — Fundação HTTP (Kit de API)

- **Status:** aceito
- **Data:** 2026-09-09
- **Issue:** Vintex-Ages/back-end#119 (`BE-FND-6`)
- **Contexto:** `.ai/architecture.md` lista "formato comum de erros e versionamento
  da API" e "política de CORS por ambiente" como decisões pendentes. As tarefas de
  rota (#76, #77, #78, #82, #85, #87, #88, #90, #91, #93, #108) já pressupõem esses
  contratos. Este ADR os fixa antes que o primeiro endpoint improvise.

## Decisões

### 1. Versionamento da API — prefixo `/api`, sem `/v1`

Todas as rotas ficam sob `/api`. Não há `/v1` enquanto não existir uma segunda
versão real. As issues já convergiram para isso (`/api/products`, `/api/auth/...`);
só a issue #69 (fechada) usava `/api/v1/pecas`.

### 2. Envelope de erro

Toda resposta de erro tem o corpo:

```json
{ "error": { "code": "STRING_CONSTANTE", "message": "texto pt-BR", "fields": { "campo": "motivo" } } }
```

- `code` é uma constante em `app/core/errors.py::ErrorCode`; o front espelha a lista.
- `message` é legível e em português.
- `fields` **só** aparece em `422` (erro de validação), mapeando campo → motivo.
- Fontes cobertas pelos handlers (`register_exception_handlers`): `AppError` e
  subclasses, `RequestValidationError` (→ `422 VALIDATION_ERROR`), `HTTPException`
  e qualquer `Exception` não tratada (→ `500 INTERNAL_ERROR`, sem stack para o cliente).

Controllers e repositories levantam `AppError`/`NotFound`/`Conflict`/`Unauthorized`/
`Forbidden`/`ValidationError`. A rota não monta `HTTPException` nem decide status.

### 3. Paginação

- Query params: `page` (≥ 1, default 1) e `page_size` (1..100, default 20).
- Valor fora de faixa → `422 VALIDATION_ERROR` (via a dependency `page_params`).
- Resposta: `Page[T]` → `{ "items": [...], "page", "page_size", "total" }`.
- `paginate(db, stmt, params)` faz **uma consulta de dados + uma de contagem** —
  nunca uma por linha.

### 4. Prefixo de rota do próprio usuário

- `/api/auth/*` — só ações de credencial: `register`, `login`, `logout`.
- `/api/users/me/*` — todo recurso do usuário logado.
- Consequência: a issue #84 (`GET /api/auth/me`) passa a ser `GET /api/users/me`.

### 5. CORS por ambiente

`settings.CORS_ORIGINS` (env `CORS_ORIGINS`), default `*`. Em produção informa-se a
lista separada por vírgula. O código não muda entre ambientes, só a variável.

### 6. Fronteira de transação

`get_db` apenas cede e fecha a sessão. O **controller** chama `db.commit()` no
sucesso de uma operação mutável e deixa o `rollback` para o tratamento de exceção
(a sessão é descartada no `finally`). Repositories não commitam.

## Fora deste ADR

- Autenticação/autorização JWT — issue #72 (`BE-FND-3`). Este kit só reserva o
  ponto de encaixe (`optional_user` / `require_auth`) nas rotas de leitura públicas.
- Padrão de migrations e ciclo de ambientes.
- Estratégia de testes com banco.

## Consequências

- `app/core/errors.py` e `app/core/pagination.py` passam a ser dependência de
  toda rota; mudanças neles são revisadas como mudança de contrato.
- As issues #84 e #90 precisam de ajuste de texto (ver descrição da #119).
- `.ai/architecture.md` foi atualizado: itens 1 e 4 saíram de "pendentes".
