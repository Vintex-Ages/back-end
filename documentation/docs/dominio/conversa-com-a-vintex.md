---
sidebar_position: 6
---

# Conversa com a Vintex

Fonte de verdade: `AssistantController.chat` (`app/controllers/assistant_controller.py`), `app/services/chat_quota.py` e as issues [#149](https://github.com/Vintex-Ages/back-end/issues/149) (a busca do chat) e [#258](https://github.com/Vintex-Ages/back-end/issues/258) (a cota).

`POST /api/ai/chat` recebe a conversa (`messages`) e responde em SSE (`text/event-stream`), um evento por linha `data:`. A pergunta é a última mensagem de quem usa; a resposta são as cinco peças mais próximas dela no catálogo ([Busca por semelhança](./busca-por-semelhanca)). Nunca inventa peça, preço ou loja (RN-65).

**Não exige login** (RN-65): o chat é acessível do catálogo público. Com sessão, a rota sabe quem pergunta, e isso só muda a cota.

## Eventos

| `type` | Quando | Campos |
|---|---|---|
| `products` | a busca respondeu, mesmo sem nada parecido | `products`: as peças, no formato do feed |
| `error` | sem pergunta, ou falha do provedor de IA | `message` |
| `error` com `code: quota_exceeded` | a cota do dia acabou | `message`, `retry_at` (ISO 8601, UTC) |
| `done` | sempre, por último | — |

A conexão sempre termina em `done`, e nenhum desses casos vira `500`: a rota responde `200` e o motivo vai no evento. É o contrato que o front lê (`vintexAiService`, front-end#199): com `code: quota_exceeded`, mostra o aviso de cota e trava o envio até `retry_at`.

## Cota do dia

O provedor de IA roda na camada gratuita, que dá **50 requisições por dia ao projeto inteiro**, somando o chat, a análise da foto no cadastro e o vetor da peça publicada. Sem cota, uma pessoa que fizesse 50 perguntas zerava o dia, e o vendedor que cadastrasse uma peça depois recebia falha na análise da foto.

Por isso o chat tem duas cotas por dia, as duas configuráveis ([Configuração](../arquitetura/configuracao)):

| Variável | Padrão | Conta |
|---|---|---|
| `CHAT_QUOTA_PER_PERSON` | `5` | perguntas de cada pessoa |
| `CHAT_QUOTA_PER_DAY` | `40` | perguntas de todo mundo somadas |

**40 e não 50** deixa margem diária para a análise de foto e o vetor da peça: a cota do chat acabar não derruba o cadastro. A sugestão de anúncio (`POST /api/ai/listing-suggestions`) não passa pela cota, e continua exigindo login.

- **Quem é a pessoa**: logada, pelo id (`user:<id>`); visitante, pela origem da requisição (`ip:<endereço>`). Um token inválido conta como visitante, como em qualquer rota pública. A cota pela origem não segura quem quiser burlar (outra rede, outra máquina), e segura o uso normal.
- **O dia é o do UTC**: a cota volta à meia-noite UTC, 21h de Brasília. A mensagem diz isso em horário de Brasília ("Volta a funcionar em 25/10 às 21h"), e `retry_at` leva o instante exato.
- **Pergunta recusada não conta**: nem para a pessoa, nem para o projeto, e não chega ao provedor. Recusada pela cota do projeto, a pergunta também não gasta a da pessoa.
- **Erro de configuração não gasta cota**: sem provedor configurado (`AI_PROVIDER=unavailable`), a resposta é `error` sem contar nada, porque nenhuma requisição sairia.
- **Falha do provedor gasta**: a pergunta chegou a ele e ocupou uma requisição do dia.

A contagem fica na tabela `ai_chat_usage`, uma linha por dia e chave (a chave do projeto é `projeto`). Conferir e somar é um comando só (`INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limite`): duas perguntas ao mesmo tempo na última vaga, só uma leva.

### Atrás de proxy

A origem é o `request.client.host` que o uvicorn entrega. Atrás de um proxy reverso, ele só é o endereço de quem pergunta se o uvicorn confiar no `X-Forwarded-For` do proxy (`--forwarded-allow-ips` ou `FORWARDED_ALLOW_IPS`). Sem isso, todo visitante sem conta chega com o endereço do proxy e divide **uma** cota por pessoa. Quem está logado não é afetado.

## Cota do provedor (429)

Quando a cota do provedor acaba, ele responde `429 RESOURCE_EXHAUSTED`. Na análise da foto, isso conta como indisponibilidade, igual ao `503`: aciona a cadeia de modelos de `GOOGLE_VISION_MODEL` e, se todos falharem, a rota devolve o mesmo `503 AI_UNAVAILABLE` ([Provedor de IA](../arquitetura/provedor-ia#indisponibilidade-503-e-429)). No chat, o embedding não tem cadeia, e o `429` vira o `error` de falha do provedor.

## Testar localmente

A busca compara vetores, o que só o Postgres faz: `tests/test_assistant_chat.py` e `tests/test_chat_quota.py` rodam com `TEST_POSTGRES_URL`. Para ver a cota no Swagger (`/docs`), baixe `CHAT_QUOTA_PER_PERSON` no `.env` (por exemplo, `2`), reinicie a API e pergunte três vezes: a terceira resposta é o `error` com `quota_exceeded`. Para zerar o dia: `DELETE FROM ai_chat_usage;`.
