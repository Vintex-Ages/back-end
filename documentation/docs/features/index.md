---
title: Features
slug: /features
sidebar_position: 1
---

# Features do back-end

Este catálogo diferencia endpoints disponíveis, capacidades técnicas já
implementadas e ferramentas de desenvolvimento. Uma fundação técnica não
significa que exista uma operação pública correspondente.

## API e domínio

| Feature | Estado | Referência |
| --- | --- | --- |
| Feed paginado de produtos ativos, ordenado por recente | Disponível em `GET /api/products` | [PR #126](https://github.com/Vintex-Ages/back-end/pull/126) |
| Catálogo de estilos | Disponível em `GET /api/styles` | [PR #122](https://github.com/Vintex-Ages/back-end/pull/122) |
| Núcleo de autenticação JWT e autorização por papel | Dependências de segurança implementadas; não há rotas de login/cadastro conectadas | [PR #128](https://github.com/Vintex-Ages/back-end/pull/128) · [ADR 0002](https://github.com/Vintex-Ages/back-end/blob/develop/.ai/adr/0002-autenticacao-jwt.md) |

## Capacidades técnicas

| Feature | Estado | Referência |
| --- | --- | --- |
| Abstração do provedor de IA | Implementada; `UnavailableAIProvider` é o padrão enquanto nenhum provedor real for configurado | [Provedor de IA](../arquitetura/provedor-ia.md) · [PR #153](https://github.com/Vintex-Ages/back-end/pull/153) |
| Análise assíncrona de imagens de produtos | Pipeline e consulta de status implementados; depende do fluxo de cadastro da peça para iniciar a análise | [PR #155](https://github.com/Vintex-Ages/back-end/pull/155) |
| Infraestrutura local de teste | Makefile, Docker Compose, LocalStack, MiniStack e base Terraform para desenvolvimento local | [Teste local](../infraestrutura/teste-local.md) · [PR #182](https://github.com/Vintex-Ages/back-end/pull/182) · [PR #183](https://github.com/Vintex-Ages/back-end/pull/183) |

## Ferramentas de desenvolvimento

| Feature | Estado | Referência |
| --- | --- | --- |
| Captura de uso de IA com Cognitrace | Logger habilitado no workspace; logs detalhados permanecem locais. O histórico público dos PRs foi revisado manualmente | [Integração Cognitrace](./cognitrace.md) · [Histórico por PR](./uso-de-ia-por-pr.md) |

Para novas features, acrescente uma entrada nesta página e uma referência
detalhada quando houver contrato, fluxo ou decisão que mereça documentação
própria.
