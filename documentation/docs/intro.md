---
slug: /
sidebar_position: 1
---

# Vintex — Back-end

Documentação viva do back-end, gerada a partir de `documentation/` neste repositório (VE-25, [#176](https://github.com/Vintex-Ages/back-end/issues/176)).

Todo PR que altera um caminho listado em [`path-map.json`](https://github.com/Vintex-Ages/back-end/blob/develop/documentation/path-map.json) recebe um comentário automático apontando qual página deveria ser revisada — informativo, nunca bloqueia o merge. Ver o workflow [`documentation-draft.yml`](https://github.com/Vintex-Ages/back-end/blob/develop/.github/workflows/documentation-draft.yml).

## Onde começar

- [Fundação HTTP](arquitetura/fundacao-http) — envelope de erro, paginação, prefixo `/api`.
- [Provedor de IA](arquitetura/provedor-ia) — abstração `AIProvider`, `UnavailableAIProvider`.
- [Infraestrutura de teste local](infraestrutura/teste-local) — Makefile, Compose `vintex-infra`, Terraform, LocalStack, MiniStack.

## Sobre o uso de IA neste portal

A integração com o addon **Cognitrace**, que popula automaticamente páginas a partir do uso de IA no desenvolvimento, é escopo da issue [VE-28 (#179)](https://github.com/Vintex-Ages/back-end/issues/179). Este portal já está estruturado como Markdown simples em `docs/` para receber esse conteúdo sem mudança de formato.
