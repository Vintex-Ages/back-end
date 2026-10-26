---
sidebar_position: 3
---

# Configuração por ambiente

Fonte de verdade: `app/config.py` (`Settings`, Pydantic Settings) e o modelo `.env.example`. Toda configuração vem do ambiente ou do `.env`; o código não muda entre ambientes, e nenhum segredo real fica no repositório.

Para rodar localmente: `cp .env.example .env` (ver o README).

## Variáveis

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `DATABASE_URL` | Postgres local | conexão do SQLAlchemy e do Alembic |
| `APP_ENV` | `development` | `production` liga as recusas de segredo padrão (abaixo) |
| `APP_DEBUG`, `APP_PORT` | `true`, `8000` | servidor local |
| `CORS_ORIGINS` | `*` | origens permitidas, separadas por vírgula ([Fundação HTTP](./fundacao-http#cors)) |
| `JWT_SECRET`, `JWT_ALGORITHM` | `dev-only-change-me`, `HS256` | assinatura do token ([ADR 0002](https://github.com/Vintex-Ages/back-end/blob/develop/.ai/adr/0002-autenticacao-jwt.md)) |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | `30`, `30` | validade da sessão |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | `admin@vintex.example.com`, vazio | conta da administradora criada pelo seed ([Autorização por papel](./fundacao-http#autorização-por-papel)) |
| `AI_PROVIDER`, `GOOGLE_*` | `unavailable` | provedor de IA da API ([Provedor de IA](./provedor-ia)) |
| `CHAT_QUOTA_PER_PERSON`, `CHAT_QUOTA_PER_DAY` | `5`, `40` | perguntas ao chat por dia, por pessoa e somadas; menos de 1 é recusado ([Cota do dia](../dominio/conversa-com-a-vintex#cota-do-dia)) |
| `PRICE_SUGGESTION_MIN_BASE` | `3` | mínimo de peças parecidas para a sugestão de preço devolver uma faixa ([Sugestão de preço](../dominio/sugestao-de-preco)) |
| `AI_ANALYSIS_QUEUE_URL`, `SQS_ENDPOINT_URL`, `AI_WORKER_PROVIDER`, `FREELLMAPI_*` | vazios / `unavailable` | fila e worker de análise de imagens ([Mensageria](../infraestrutura/mensageria)) |
| `PUBLIC_BASE_URL`, `MEDIA_INTERNAL_BASE_URL` | vazios | base das URLs de mídia devolvidas e baixadas pelo servidor |
| `AWS_REGION`, `S3_ENDPOINT_URL`, `MEDIA_BUCKET` | `us-east-2`, vazio | storage de mídia; sem `MEDIA_BUCKET`, as rotas de mídia respondem 503 |

## Recusas em produção

Com `APP_ENV=production`, dois padrões de desenvolvimento são recusados em vez de usados em silêncio:

- **`JWT_SECRET` igual ao padrão** derruba a aplicação na inicialização (`_recusa_segredo_padrao_em_producao`).
- **`SEED_ADMIN_PASSWORD` vazio** faz `python -m app.seeds.admin` recusar rodar: a conta da administradora não pode nascer com a senha de desenvolvimento ([#61](https://github.com/Vintex-Ages/back-end/issues/61)).

## Nos testes

`tests/conftest.py` fixa `DATABASE_URL` (SQLite em memória) e `AI_PROVIDER=unavailable` antes de importar a aplicação, para os testes não herdarem o `.env` de quem roda. Sem isso, com `AI_PROVIDER=google` e uma chave real no `.env`, publicar uma peça num teste chamaria o Gemini ([#245](https://github.com/Vintex-Ages/back-end/issues/245)). Teste que precisa de IA troca o provider por um dublê.

Variável nova entra nos dois lugares: no `Settings`, com comentário dizendo para que serve, e no `.env.example`, sem valor real.
