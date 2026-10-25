---
sidebar_position: 5
---

# Busca por semelhança

Fonte de verdade: `ProductRepository.find_similar` (`app/repositories/product_repository.py`) e as issues [#149](https://github.com/Vintex-Ages/back-end/issues/149) (a busca do chat) e [#246](https://github.com/Vintex-Ages/back-end/issues/246) (paginação, filtros e distância).

Cada peça pode ter um **embedding**: um vetor que representa o que ela é (nome, descrição, marca, cor, tamanho, estilo), gerado pelo provedor de IA e guardado em `products.embedding` (pgvector). Achar peças parecidas com algo, seja a pergunta do chat, uma foto ou o perfil de estilo, é gerar o vetor desse algo e ordenar o catálogo pela **distância de cosseno** até ele: 0 é idêntica, e quanto maior, menos parecida.

## O que a consulta faz

`find_similar(vetor, modelo, params, filtros)` devolve `(linhas, total)`:

- **Página com total**, como o feed (`page`, `page_size`).
- **Os mesmos filtros do catálogo**, somados por E com a semelhança: categoria, tamanho, marca, conservação, cor, preço, loja, cidade e estado. São os do feed, montados no mesmo lugar (`_condicoes_do_catalogo`).
- **A distância em cada linha** (`distance`). Quem chama decide como rotular: direto, alternativa, "parecido com".
- **Só peça ativa**, como o feed. Rascunho, reservada, vendida e despublicada ficam de fora ([Situações da peça](./situacoes-da-peca)).
- **Ordem estável**: distância e, no empate, o `id`. A paginação não repete nem pula peça.

## Quando a peça ganha vetor

Desde a [#245](https://github.com/Vintex-Ages/back-end/issues/245), quem grava o vetor é a própria publicação (`app/services/product_embedding.py`). Antes, só o backfill gravava, rodado à mão, e a peça que o vendedor publicava ficava fora do chat sem erro nenhum.

| Momento | O que acontece com o vetor |
|---|---|
| Publicar (rascunho ou despublicada → ativo) | gera, se a peça não tem vetor ou tem vetor de outro modelo; republicar com vetor do modelo ativo **não chama a IA** |
| Despublicar | fica como está (RN-52) |
| Editar nome, descrição, marca, cor, tamanho ou estilo de peça **ativa** | gera de novo na hora |
| Editar esses campos com a peça **fora do ar** | apaga; gera ao publicar |
| Editar só preço, categoria ou fotos | nada muda: não entram no texto do vetor |

- **O texto que vira vetor é um só** (`texto_da_peca`), usado pela publicação e pelo backfill: os vetores dos dois são comparáveis.
- **Falha da IA não bloqueia** a publicação nem a edição (RN-57): a peça fica sem vetor, e o motivo vai para o log. Sem vetor, o backfill a encontra depois. Um vetor antigo, mantido depois de uma edição que falhou, descreveria a peça de antes, e o backfill não o encontraria.
- **Sem IA configurada** (`AI_PROVIDER=unavailable`, como na staging hoje), a peça publica normalmente, sem vetor, e o log registra em nível informativo, sem alarme. Para a busca por significado funcionar num ambiente, ele precisa de um provedor de embedding e do backfill do catálogo.
- O vetor é gerado na própria requisição, e não pela fila: o worker da fila (`AI_WORKER_PROVIDER`, FreeLLMAPI) só faz análise de imagem. As rotas de publicar e editar são `def`, então a espera pelo provedor não trava o servidor.

## Só vetores do mesmo modelo

Vetores de modelos diferentes vivem em espaços diferentes: a distância entre eles é ruído com cara de resultado. A consulta só compara peças cujo `embedding_model` é o modelo ativo, o que `modelo_de_embedding()` devolve a partir de `GOOGLE_EMBEDDING_MODEL`. Peça sem vetor, ou com vetor de outro modelo, não entra.

Trocar de modelo é, então, reprocessar o catálogo: `python -m scripts.backfill_embeddings` encontra as peças sem vetor ou com outro modelo e gera de novo só elas. O script recusa `GOOGLE_EMBEDDING_MODEL` com lista (`a,b`) antes de tocar o banco: a coluna ganharia a lista inteira.

## Sem limiar de distância

**A consulta não corta por distância.** Uma busca sem nada parecido ainda devolve as peças mais próximas, e a lista não volta vazia enquanto houver catálogo que passe nos filtros (RN-61). Devolver a distância não autoriza cortar: quem precisar de um limiar o aplica do lado de quem chama, medido, como a [#231](https://github.com/Vintex-Ages/back-end/issues/231) vai fazer no chat.

Filtro que não casa com nenhuma peça devolve página vazia: aí é o filtro, e não a semelhança, e quem chama decide se oferece alternativa, como o feed faz.

## Quem usa

| Uso | Issue | Situação |
|---|---|---|
| Conversa com a Vintex (`POST /api/ai/chat`) | [#149](https://github.com/Vintex-Ages/back-end/issues/149) | as 5 mais próximas, sem filtro |
| Rotular direto e alternativa no chat | [#231](https://github.com/Vintex-Ages/back-end/issues/231) | a fazer, usa a distância |
| Filtro por atributo na conversa | [#260](https://github.com/Vintex-Ages/back-end/issues/260) | a fazer, usa os filtros |
| Recomendações pelo perfil de estilo | [#253](https://github.com/Vintex-Ages/back-end/issues/253) | a fazer, usa paginação e filtros |
| Busca por foto | [#255](https://github.com/Vintex-Ages/back-end/issues/255) | a fazer, usa paginação e filtros |
| Sugestão de preço | [#254](https://github.com/Vintex-Ages/back-end/issues/254) | a fazer, compara preços das parecidas |

## Testar localmente

`cosine_distance` só existe no Postgres com pgvector: os testes (`tests/test_find_similar.py`, `tests/test_assistant_chat.py`) rodam com `TEST_POSTGRES_URL`. Com a IA configurada no `.env`, o chat no Swagger (`POST /api/ai/chat`) usa a consulta de verdade sobre o catálogo do seed depois do backfill.
