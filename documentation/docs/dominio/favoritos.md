---
sidebar_position: 7
---

# Favoritos

Fonte de verdade: `app/controllers/favorite_controller.py`, `app/repositories/favorite_repository.py` e a issue [#252](https://github.com/Vintex-Ages/back-end/issues/252).

O comprador favorita peças para voltar a elas depois. A lista alimenta a seção de favoritos do perfil (RN-43), e o front a consulta para marcar o coração em qualquer tela. Todas as rotas exigem login (RN-27) e só enxergam os favoritos de quem pede.

| Rota | O que faz | Resposta |
| --- | --- | --- |
| `GET /api/users/me/favorites` | lista paginada, mais recente primeiro | `200` com `{ items, page, page_size, total }` |
| `PUT /api/users/me/favorites/{product_id}` | favorita a peça | `204` sem corpo · `404 PRODUCT_NOT_FOUND` |
| `DELETE /api/users/me/favorites/{product_id}` | desfavorita a peça | `204` sem corpo |

Sem token, as três respondem `401 AUTH_REQUIRED`, com o mesmo corpo das outras ações protegidas.

## O item da lista

É o **mesmo item do feed** (`ProductFeedItemResponse`), para o front reusar o mapeador do catálogo:

```json
{
  "id": 7,
  "name": "Jaqueta jeans",
  "price": 159.9,
  "cover_image_url": "https://.../7.jpg",
  "status": "reservado",
  "store": { "id": 3, "name": "Roupa Rodada", "verified": true }
}
```

## As decisões

- **Chave composta `(user_id, product_id)`, sem `id` próprio.** O `PUT` é um `INSERT ... ON CONFLICT DO NOTHING`: favoritar o que já está favoritado não duplica, sem consulta prévia e sem corrida num duplo clique.
- **As duas escritas são idempotentes.** Favoritar duas vezes responde `204` nas duas. Desfavoritar o que não está favoritado, ou uma peça que nem existe, também responde `204`. A tela não precisa saber o estado anterior para agir.
- **Valem as situações do detalhe público** (`ProductController.PUBLICOS`: `ativo`, `reservado`, `vendido`; ver [Situações da peça](./situacoes-da-peca)). Só se favorita o que o detalhe mostra: `rascunho` e `despublicado` respondem `404` no `PUT`, como no detalhe.
- **Peça vendida ou reservada continua na lista, com o `status` dizendo** (RN-44): sinalizar, não esconder.
- **Peça despublicada sai da lista, mas a linha fica.** Se o vendedor republicar, ela volta para os favoritos. Se a peça for apagada, a linha vai junto (`ON DELETE CASCADE`).

## O aviso ao anunciante

Favoritar avisa o vendedor dono da peça (RN-85), uma vez por pessoa e por peça, no mesmo commit do favorito. Desfavoritar não avisa. Ver [Notificações](./notificacoes) ([#261](https://github.com/Vintex-Ages/back-end/issues/261)).
