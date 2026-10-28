---
sidebar_position: 6
---

# Conversa com a Vintex

Fonte de verdade: `AssistantController.chat` (`app/controllers/assistant_controller.py`), `app/services/ai/search_interpretation.py`, `app/services/chat_quota.py` e as issues [#149](https://github.com/Vintex-Ages/back-end/issues/149) (a busca do chat), [#260](https://github.com/Vintex-Ages/back-end/issues/260) (o filtro) e [#258](https://github.com/Vintex-Ages/back-end/issues/258) (a cota).

`POST /api/ai/chat` recebe a conversa (`messages`) e responde em SSE (`text/event-stream`), um evento por linha `data:`. A pergunta é a última mensagem de quem usa. O que ela pede de objetivo vira filtro, e a resposta são as cinco peças que passam no filtro, ordenadas por semelhança ([Busca por semelhança](./busca-por-semelhanca)). Nunca inventa peça, preço ou loja (RN-65).

**Não exige login** (RN-65): o chat é acessível do catálogo público. Com sessão, a rota sabe quem pergunta, e isso só muda a cota.

## Eventos

| `type` | Quando | Campos |
|---|---|---|
| `interpreted` | a pergunta foi interpretada | `filters` (nomes do catálogo: `category`, `price_max`...), `similarity` |
| `text` | nada casou com os filtros e as peças são alternativas | `delta`: o aviso, com o que faltou |
| `products` | a busca respondeu, mesmo sem nada parecido | `products`: as peças, no formato do feed; `match_type`: `exact` ou `fallback` |
| `error` | sem pergunta, ou falha do provedor de IA | `message` |
| `error` com `code: quota_exceeded` | a cota do dia acabou | `message`, `retry_at` (ISO 8601, UTC) |
| `done` | sempre, por último | — |

A ordem é `interpreted`, `text` (só nas alternativas), `products` e `done`. A conexão sempre termina em `done`, e nenhum desses casos vira `500`: a rota responde `200` e o motivo vai no evento. É o contrato que o front lê (`vintexAiService`, front-end#199): com `code: quota_exceeded`, mostra o aviso de cota e trava o envio até `retry_at`.

## Filtro e similaridade

Antes da [#260](https://github.com/Vintex-Ages/back-end/issues/260), tudo era similaridade: "tênis verde até 400" devolvia o mais parecido no espaço vetorial, e um tênis branco de outro preço podia vir primeiro. Agora a regra é **filtro rígido corta, similaridade ordena**.

1. **A IA lê a pergunta** (`stream_interpret_search`) e separa o objetivo do subjetivo. Ela não busca nem sugere peça: só preenche os campos.
2. **Viram filtro**: categoria, cor, tamanho, conservação, marca e faixa de preço. São filtros do feed (RN-40), e a lista é a do card. Localização e loja ficam de fora.
3. **Só valor do catálogo vira filtro.** Categoria, cor, tamanho e conservação têm vocabulário fechado (`app/constants/catalog.py`), e um valor fora dele é descartado, em vez de cortar o catálogo inteiro. Caixa e acento não importam ("verde" vira "Verde"). Faixa de preço invertida ou negativa também é descartada.
4. **O resto é `similarity`** (estilo, ocasião, uso: "para festa", "de corrida"). O front mostra como "parecido com: …".
5. **A busca** filtra e ordena pela distância até o vetor da pergunta inteira. Dentro do filtro, os atributos objetivos são iguais em todas as peças, e quem ordena é o resto.

A conversa anterior vai junto para a IA (os 6 últimos turnos): "e em vermelho?", depois de "tênis de corrida", vira `Sapatos` e `Vermelho`.

**Nada casou com o filtro** (RN-61): a resposta nunca vem vazia enquanto houver catálogo. Primeiro, só a categoria: quem pediu "bota bege" e não tem nenhuma vê botas de outra cor. Se nem a categoria tiver peça, o catálogo todo. Nos dois casos, `products` vem com `match_type: "fallback"`, e um evento `text` antes diz o que faltou: "Não encontrei peças com Sapatos e Bege. Estas são alternativas, as mais parecidas com o que você pediu."

**A interpretação falhou** (modelo fora do ar, cota do provedor): a busca segue só por similaridade, sem o evento `interpreted`, como era antes. A IA ajuda, mas não trava a conversa (RN-57).

| Pergunta (seed, Gemini real) | Filtros lidos | Primeira peça |
|---|---|---|
| tênis verde até 400 | Sapatos, Verde, até 400 | Zara Tênis Verde, R$ 374,79 |
| vestido preto para festa | Roupas, Preto; parecido com "para festa" | Farm Vestido Preto (igual a antes) |
| tenis de corrida masculino 42 | Sapatos, 42; parecido com "de corrida masculino" | Lacoste Sapatênis Branco, 42 (antes vinha um tênis 38) |
| bota bege | Sapatos, Bege: nenhuma | alternativas: C&A Bota Branco |

A interpretação usa os modelos de geração de `GOOGLE_VISION_MODEL`, os mesmos da análise de foto, com o mesmo fallback no `503` e no `429` ([Provedor de IA](../arquitetura/provedor-ia#indisponibilidade-503-e-429)).

## Texto de terceiro é dado, não instrução

A pergunta e a conversa anterior são escritas por quem usa o site, e o modelo não deve obedecê-las. Desde a [#262](https://github.com/Vintex-Ages/back-end/issues/262), `montar_pergunta` envolve a conversa e a pergunta nas marcas `<<<INICIO_DO_TEXTO_DE_TERCEIRO>>>` e `<<<FIM_DO_TEXTO_DE_TERCEIRO>>>`, e `INTERPRET_SEARCH_PROMPT` diz que o bloco é dado a interpretar: pedido para ignorar regras, mudar o formato da resposta ou responder outra coisa é ignorado. Marcador escrito dentro do texto é neutralizado, para o conteúdo não fechar o bloco e escrever fora dele. Instrução e dado vão em partes separadas da chamada (`app/services/ai/untrusted_text.py`).

A descrição da peça não passa pelo prompt da conversa: ela é parte do texto que vira vetor e volta ao card como dado. Se voltar como turno do chat, volta dentro do mesmo bloco.

## Cota do dia

O provedor de IA roda na camada gratuita, que dá **50 requisições por dia ao projeto inteiro**, somando o chat, a análise da foto no cadastro e o vetor da peça publicada. Sem cota, uma pessoa que fizesse 50 perguntas zerava o dia, e o vendedor que cadastrasse uma peça depois recebia falha na análise da foto.

Por isso o chat tem duas cotas por dia, as duas configuráveis ([Configuração](../arquitetura/configuracao)):

| Variável | Padrão | Conta |
|---|---|---|
| `CHAT_QUOTA_PER_PERSON` | `5` | perguntas de cada pessoa |
| `CHAT_QUOTA_PER_DAY` | `40` | perguntas de todo mundo somadas |

**40 e não 50** deixa margem diária para a análise de foto e o vetor da peça: a cota do chat acabar não derruba o cadastro. A sugestão de anúncio (`POST /api/ai/listing-suggestions`) não passa pela cota, e continua exigindo login.

**Cada pergunta são duas chamadas ao provedor** desde a #260: a interpretação, num modelo de geração, e o vetor, no modelo de embedding. A cota conta perguntas, não chamadas. A interpretação divide os modelos de geração com a análise de foto, e é por isso que o `429` num modelo faz tentar o próximo da lista.

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

A busca compara vetores, o que só o Postgres faz: `tests/test_assistant_chat.py`, `tests/test_chat_filtros.py` e `tests/test_chat_quota.py` rodam com `TEST_POSTGRES_URL`. A leitura da pergunta e o provedor do Google, em `tests/test_chat_filtros.py`, rodam sem banco e sem rede. Com `AI_PROVIDER=google` no `.env` e o catálogo com vetores (backfill), as perguntas da tabela acima no Swagger mostram o `interpreted` e as peças filtradas. Para ver a cota no Swagger (`/docs`), baixe `CHAT_QUOTA_PER_PERSON` no `.env` (por exemplo, `2`), reinicie a API e pergunte três vezes: a terceira resposta é o `error` com `quota_exceeded`. Para zerar o dia: `DELETE FROM ai_chat_usage;`.
