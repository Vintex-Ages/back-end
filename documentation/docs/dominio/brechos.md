---
sidebar_position: 8
---

# Brechós

Fonte de verdade: `app/controllers/store_controller.py`, `app/repositories/store_repository.py` e as issues [#142](https://github.com/Vintex-Ages/back-end/issues/142) (perfil público) e [#256](https://github.com/Vintex-Ages/back-end/issues/256) (listagem com busca).

Cada vendedor tem uma loja (RN-02). As rotas abaixo são públicas e funcionam deslogado (RN-26).

| Rota | O que faz |
| --- | --- |
| `GET /api/stores?q=` | lista os brechós em ordem de nome, paginada, com busca por nome |
| `GET /api/stores/{store_id}` | perfil público, com o selo e as métricas |
| `GET /api/stores/{store_id}/products` | peças `ativo` da loja, mais recentes primeiro |

## A listagem

```json
{
  "items": [{
    "id": 7,
    "name": "Garimpo da Redenção",
    "description": "Garimpo no Bom Fim.",
    "logo_url": "https://.../logo.png",
    "verified": true,
    "city": "Porto Alegre",
    "state": "RS",
    "active_count": 5
  }],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

- **`q` casa só o nome da loja**, por parte do nome e sem diferenciar maiúscula. No Postgres também ignora acento (`redencao` acha "Redenção"). Cidade fica de fora, declarado na #256. Filtrar por cidade é o filtro do catálogo.
- `q` ausente ou em branco lista todos. Mais de 100 caracteres responde `422`.
- **`city` e `state` são nulos quando a loja não tem endereço** (`stores.address_id` é anulável). A loja continua na lista.
- A busca devolve as lojas. As peças de uma loja saem de `GET /api/stores/{id}/products`; as duas juntas cumprem a RN-42.

## A contagem de peças ativas

`active_count` conta **só peça `ativo`**. Reservada, vendida, despublicada e rascunho ficam de fora: a RN-44 manda sinalizar a peça indisponível, então a contagem diz quantas estão à venda agora, e não quantas já existiram.

O perfil devolve o mesmo número em `metrics.active_count`. O campo antigo `metrics.products_listed` tem o mesmo valor: ele contava tudo que não fosse rascunho, incluindo vendida e despublicada, e o front o mostrava como "peças ativas". Ficou corrigido em vez de removido, para não quebrar quem ainda lê o nome antigo.

## A avaliação no perfil

`metrics.rating` é a média das estrelas, com uma casa, e `metrics.rating_count` quantas avaliações a loja tem. Loja sem avaliação devolve `rating: null`, não zero. Ver [Avaliação da loja](./avaliacao-da-loja) ([#267](https://github.com/Vintex-Ages/back-end/issues/267)).
