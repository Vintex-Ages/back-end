---
sidebar_position: 8
---

# Loja do vendedor

Fonte de verdade: `app/views/store_routes.py` (`me_router`), `app/controllers/store_controller.py` e `app/schemas/store_schema.py`. A criação e a leitura vêm da BE-US006-1 ([#141](https://github.com/Vintex-Ages/back-end/issues/141)); a edição, da BE-US006-3 ([#221](https://github.com/Vintex-Ages/back-end/issues/221)).

A loja do próprio vendedor vive sob `/api/users/me/store` (ADR 0001 §4) e exige login. Um vendedor tem uma loja.

## Rotas

| Rota | O que faz |
| --- | --- |
| `POST /api/users/me/store` | cria a loja: nome, descrição, logo, chave Pix, endereço, documento e versão do contrato |
| `GET /api/users/me/store` | a própria loja, com chave Pix, documento e selo; `404 STORE_NOT_FOUND` sem loja |
| `PATCH /api/users/me/store` | edita nome, descrição, `logo_url`, endereço e chave Pix; `404 STORE_NOT_FOUND` sem loja |

## Edição

- **PATCH parcial:** só o que vem no corpo muda. Campo ausente não é apagado, e corpo vazio devolve a loja como estava.
- **`null` explícito limpa o campo.** É como se tira a logo (`"logo_url": null`). O nome é a exceção: é obrigatório, e `"name": null` responde 422.
- **O endereço vem inteiro**, com os mesmos campos do cadastro, e substitui o que havia. A loja que já tinha endereço reaproveita a linha em `addresses`; a que não tinha ganha uma. A UF é gravada em maiúscula, como no cadastro.
- **O documento não é alterável por aqui.** `document_type` e `document_value` mudam a identidade do vendedor e têm unicidade, então são outra rota com regra própria. Mandá-los responde 422 (`extra="forbid"`), em vez de serem ignorados com uma resposta 200 que diria que deu certo.
- A logo nova sobe antes por `POST /api/users/me/media` com `kind=logo`, como no cadastro (ver [Mídia](./midia)).

## Transação

O `StoreRepository` não faz commit, como o resto do app (ADR 0001 §6): `save` adiciona e dá `flush`, e quem fecha a transação é o `StoreController`. Antes o `save` commitava, e um `PATCH` não teria controle da própria transação.
