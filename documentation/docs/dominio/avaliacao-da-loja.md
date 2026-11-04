---
sidebar_position: 11
---

# Avaliação da loja

Fonte de verdade: `app/controllers/store_rating_controller.py`, `app/repositories/store_rating_repository.py`, `app/models/store_rating.py` e a issue [#267](https://github.com/Vintex-Ages/back-end/issues/267).

O comprador dá de 1 a 5 estrelas à loja de um pedido que recebeu. A média e a contagem aparecem no perfil público da loja (RN-74).

| Rota | O que faz | Resposta |
| --- | --- | --- |
| `POST /api/stores/{store_id}/ratings` | avalia a loja por um pedido entregue | `201` com `{ id, store_id, order_id, score, created_at }` |
| `GET /api/stores/{store_id}` | perfil da loja | `metrics.rating` e `metrics.rating_count` |

Corpo do `POST`:

```json
{ "order_id": 31, "score": 4 }
```

## Erros

| Status | `code` | Quando |
| --- | --- | --- |
| `401` | `AUTH_REQUIRED` | sem login (RN-27) |
| `403` | `RATING_NOT_ALLOWED` | o pedido não é de quem pede, não é desta loja, não existe ou ainda não foi entregue |
| `404` | `STORE_NOT_FOUND` | a loja não existe |
| `409` | `ALREADY_RATED` | este pedido já foi avaliado |
| `422` | `VALIDATION_ERROR` | `score` fora de 1 a 5, ou não inteiro |

## As decisões

- **Só estrelas, sem comentário** (RN-75). A tabela `store_ratings` não tem coluna de texto. Um `comment` no corpo é ignorado.
- **Só quem comprou avalia** (RN-76), e "comprou" quer dizer **pedido entregue**: o status derivado `concluido`, três dias depois da aprovação do comprovante (RN-83 simula a entrega; ver [Pedidos do comprador](./pedidos-do-comprador#linha-do-tempo)). A regra é a mesma da tela do pedido (`status_atual` em `order_controller.py`). Pedido recém-aprovado ainda não avalia.
- **Uma avaliação por pedido.** Dois pedidos entregues da mesma loja avaliam duas vezes. O `UNIQUE` em `order_id` é a garantia, inclusive em dois cliques ao mesmo tempo, e o `IntegrityError` vira `409`.
- **O `403` é o mesmo para todo pedido que não serve.** Pedido de outra pessoa, de outra loja, inexistente ou não entregue respondem igual: uma resposta diferente confirmaria que o id existe.
- **A nota fora de 1 a 5 é recusada pelo banco**, pelo CHECK `ck_store_ratings_score`, e não só pelo schema.
- **Loja sem avaliação devolve `rating: null`**, e não zero: zero diria que a loja foi mal avaliada. `rating` vem com uma casa decimal.
