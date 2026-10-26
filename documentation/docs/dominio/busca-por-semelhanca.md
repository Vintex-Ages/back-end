---
sidebar_position: 5
---

# Busca por semelhança

Fonte de verdade: `ProductRepository.find_similar` (`app/repositories/product_repository.py`) e as issues [#149](https://github.com/Vintex-Ages/back-end/issues/149) (a busca do chat) e [#246](https://github.com/Vintex-Ages/back-end/issues/246) (paginação, filtros e distância).

Cada peça pode ter um **embedding**: um vetor que representa o que ela é (nome, categoria, descrição, marca, cor, tamanho, conservação, estilo, cidade e preço), gerado pelo provedor de IA e guardado em `products.embedding` (pgvector). Achar peças parecidas com algo, seja a pergunta do chat, uma foto ou o perfil de estilo, é gerar o vetor desse algo e ordenar o catálogo pela **distância de cosseno** até ele: 0 é idêntica, e quanto maior, menos parecida.

## O que a consulta faz

`find_similar(vetor, modelo, params, filtros)` devolve `(linhas, total)`:

- **Página com total**, como o feed (`page`, `page_size`).
- **Os mesmos filtros do catálogo**, somados por E com a semelhança: categoria, tamanho, marca, conservação, cor, preço, loja, cidade e estado. São os do feed, montados no mesmo lugar (`_condicoes_do_catalogo`).
- **A distância em cada linha** (`distance`). Quem chama decide como rotular: direto, alternativa, "parecido com".
- **Só peça ativa**, como o feed. Rascunho, reservada, vendida e despublicada ficam de fora ([Situações da peça](./situacoes-da-peca)).
- **Ordem estável**: distância e, no empate, o `id`. A paginação não repete nem pula peça.

## Quando a peça ganha vetor

Desde a [#245](https://github.com/Vintex-Ages/back-end/issues/245), a própria publicação pede o vetor (`app/services/product_embedding.py`). Antes, só o backfill gravava, rodado à mão, e a peça que o vendedor publicava ficava fora do chat sem erro nenhum.

**Em segundo plano, como a análise da foto.** Publicar marca `embedding_status = pending` e responde na hora; o vetor é gerado depois da resposta (`BackgroundTasks` do FastAPI, `gerar_embedding_da_peca`), com sessão própria de banco. Não passa pela fila SQS: o worker dela (`AI_WORKER_PROVIDER`, FreeLLMAPI) só faz análise de imagem.

| Momento | O que acontece com o vetor |
|---|---|
| Publicar (rascunho ou despublicada → ativo) | `pending`, e gera em segundo plano, se a peça não tem vetor ou tem vetor de outro modelo; republicar com vetor do modelo ativo **não chama a IA** |
| Despublicar | fica como está (RN-52) |
| Editar um atributo do texto de peça **ativa** | o vetor antigo sai na hora, e o novo é gerado em segundo plano |
| Editar um atributo do texto com a peça **fora do ar** | apaga; gera ao publicar |
| Editar só as fotos | nada muda: não entram no texto |

**A situação fica registrada na peça**, como `ai_status`/`ai_error` registram a análise da foto:

| `embedding_status` | Significa |
|---|---|
| nulo | nenhuma geração pedida (rascunho, catálogo anterior à coluna, ou texto editado fora do ar) |
| `pending` | pedida, esperando o segundo plano |
| `done` | vetor gravado, do modelo em `embedding_model` |
| `failed` | a IA falhou ou não está configurada; o motivo está em `embedding_error` |

- **O texto que vira vetor é um só** (`texto_da_peca`), usado pela publicação e pelo backfill: os atributos da RN-49 (categoria, tamanho, cor, marca, conservação, cidade da loja, preço e descrição), mais o nome e o estilo, que o backfill já usava.
- **Falha da IA não bloqueia** a publicação nem a edição (RN-57): a peça fica sem vetor, com `failed` e o motivo. Sem vetor, o backfill a encontra depois e marca `done`. Por isso uma edição apaga o vetor antigo em vez de mantê-lo: ele descreveria a peça de antes, e o backfill não o encontraria.
- **Sem IA configurada** (`AI_PROVIDER=unavailable`, como na staging hoje), a peça publica normalmente e fica `failed` com "Nenhum provedor de IA configurado", e o log é informativo, sem alarme. Para a busca por significado funcionar num ambiente, ele precisa de um provedor de embedding e do backfill do catálogo.
- **Vetores gravados antes desta mudança** usaram o texto antigo (sem categoria, conservação, cidade e preço). Continuam válidos, do mesmo modelo; para refazê-los com o texto novo, basta apagar o vetor (`embedding = NULL`) e rodar o backfill.

## Só vetores do mesmo modelo

Vetores de modelos diferentes vivem em espaços diferentes: a distância entre eles é ruído com cara de resultado. A consulta só compara peças cujo `embedding_model` é o modelo ativo, o que `modelo_de_embedding()` devolve a partir de `GOOGLE_EMBEDDING_MODEL`. Peça sem vetor, ou com vetor de outro modelo, não entra.

Trocar de modelo é, então, reprocessar o catálogo: `python -m scripts.backfill_embeddings` encontra as peças sem vetor ou com outro modelo e gera de novo só elas. O script recusa `GOOGLE_EMBEDDING_MODEL` com lista (`a,b`) antes de tocar o banco: a coluna ganharia a lista inteira.

## Sem limiar de distância

**A consulta não corta por distância.** Uma busca sem nada parecido ainda devolve as peças mais próximas, e a lista não volta vazia enquanto houver catálogo que passe nos filtros (RN-61). Devolver a distância não autoriza cortar: quem precisar de um limiar o aplica do lado de quem chama, medido, como a [#231](https://github.com/Vintex-Ages/back-end/issues/231) vai fazer no chat.

Filtro que não casa com nenhuma peça devolve página vazia: aí é o filtro, e não a semelhança, e quem chama decide se oferece alternativa, como o feed faz.

## Quem usa

| Uso | Issue | Situação |
|---|---|---|
| [Conversa com a Vintex](./conversa-com-a-vintex) (`POST /api/ai/chat`) | [#149](https://github.com/Vintex-Ages/back-end/issues/149) | as 5 mais próximas, com os filtros da pergunta |
| Rotular direto e alternativa no chat | [#231](https://github.com/Vintex-Ages/back-end/issues/231) | a fazer, usa a distância |
| Filtro por atributo na conversa | [#260](https://github.com/Vintex-Ages/back-end/issues/260) | feito, usa os filtros |
| Recomendações pelo perfil de estilo (`GET /api/users/me/recommendations`) | [#253](https://github.com/Vintex-Ages/back-end/issues/253) | feito, ver abaixo |
| Busca por foto | [#255](https://github.com/Vintex-Ages/back-end/issues/255) | a fazer, usa paginação e filtros |
| Sugestão de preço | [#254](https://github.com/Vintex-Ages/back-end/issues/254) | a fazer, compara preços das parecidas |

## Recomendação pelo perfil de estilo

O "Garimpados para Você" da home ([#253](https://github.com/Vintex-Ages/back-end/issues/253)): `GET /api/users/me/recommendations?page=`, com login (RN-27). A resposta é `{ items, personalized, page, page_size, total }`, e o item é o mesmo do feed.

- **O perfil vira texto, e o texto vira vetor** (`app/services/style_profile.py`). São as preferências do tipo `estilo` que o onboarding grava, cada uma com o identificador, o rótulo e a descrição do catálogo de estilos. As peças guardam o estilo pelo mesmo identificador, e ele entra no texto do vetor delas.
- **Similaridade, não filtragem colaborativa** (RN-62): peça parecida com o perfil, não "quem comprou isto comprou aquilo", porque cada peça é única.
- **O vetor de cada perfil fica em memória** (até 128 perfis): a home chama a rota a cada carregamento, e o mesmo perfil não chama a IA de novo. Mudar o perfil muda o texto, e o texto novo gera outro vetor.
- **Nunca é erro, nunca vem vazia** enquanto houver catálogo (RN-38, RN-61). Vem o feed genérico, com `personalized: false`, em três casos: a pessoa não tem estilo no perfil; a IA falhou ao gerar o vetor do perfil; ou nenhuma peça tem vetor ainda (ambiente sem IA, como a staging).
- **Peça publicada agora aparece** na recomendação sem rodar script, porque a publicação gera o vetor dela ([#245](https://github.com/Vintex-Ages/back-end/issues/245)).

## Testar localmente

`cosine_distance` só existe no Postgres com pgvector: os testes (`tests/test_find_similar.py`, `tests/test_assistant_chat.py`) rodam com `TEST_POSTGRES_URL`. Com a IA configurada no `.env`, o chat no Swagger (`POST /api/ai/chat`) usa a consulta de verdade sobre o catálogo do seed depois do backfill.
