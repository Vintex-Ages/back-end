---
sidebar_position: 4
---

# Mídia

Fonte de verdade: `app/services/media_rules.py` (formato e tamanho), `app/services/media_storage.py` (o objeto no S3) e `app/views/media_routes.py` (as rotas), da VE-04 ([#73](https://github.com/Vintex-Ages/back-end/issues/73)) e da VE-16.

A divisão de responsabilidade é de propósito: o `MediaStorage` sobe, lê e remove bytes e não conhece regra nenhuma; formato e tamanho são do `media_rules`; a URL é do `MediaController`.

## Tipos de mídia

| `kind` | Prefixo no bucket | Formatos aceitos | Leitura |
| --- | --- | --- | --- |
| `photo` | `products/photos/` | jpeg, png, webp, heic | pública |
| `video` | `products/videos/` | mp4, quicktime | pública |
| `logo` | `stores/logos/` | jpeg, png, webp, heic | pública |
| `label` | `products/labels/` | jpeg, png, webp, heic | pública, mas **fora da galeria** ([#257](https://github.com/Vintex-Ages/back-end/issues/257)) |
| `receipt` | `payments/receipts/` | jpeg, png, webp, heic **e pdf** ([#244](https://github.com/Vintex-Ages/back-end/issues/244)) | **só a administradora** |

- **Limites:** 8 MiB por arquivo, 24 MiB por envio, até 8 arquivos. São os mesmos que a análise de IA aplica ao baixar a foto: o upload não aceita o que a IA recusaria depois.
- A foto da etiqueta é legível pela rota pública porque é por ela que o servidor baixa a foto para a IA. O que a mantém fora da vitrine é outra regra: a peça recusa essa URL em `images` (ver [Etiqueta e composição](./etiqueta-e-composicao)).
- A chave é o prefixo mais um uuid, sem extensão e sem o nome original. Por isso o comprovante grava nome e tipo em `payments` no envio (ver [Validação do comprovante](./validacao-de-comprovante#o-arquivo-do-comprovante)).

## Rotas

| Rota | Quem | O que faz |
| --- | --- | --- |
| `POST /api/users/me/media` | usuário logado | multipart `files` e `kind`; valida tudo antes de subir qualquer arquivo, para não deixar objeto órfão |
| `GET /api/media/{key}` | todo mundo | serve só os prefixos públicos; comprovante responde 404, igual a chave inexistente |
| `GET /api/admin/payments/{order_id}/receipt` | administradora | serve o comprovante vigente do pedido |

- O upload devolve `url` absoluta para os tipos públicos e `null` para o comprovante: a API não entrega endereço que ela mesma nega.
- As leituras saem com `X-Content-Type-Options: nosniff`. O tipo é o que o cliente declarou no upload, e sem `nosniff` o navegador poderia renderizar como HTML um arquivo mandado como imagem, servido da nossa origem.
- Sem `MEDIA_BUCKET` configurado, as rotas respondem `503 SERVICE_UNAVAILABLE`, e não 500 (`get_media_storage`). Ver [Configuração por ambiente](../arquitetura/configuracao).
