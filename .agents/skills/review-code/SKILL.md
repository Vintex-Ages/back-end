---
name: review-code
description: Revisa mudanças do backend Vintex quanto a correção, segurança, arquitetura, persistência e testes. Use em pedidos de code review, revisão de diff ou preparação para merge.
---

# Review Code

Leia `.ai/architecture.md`, `.ai/coding-rules.md` e `.ai/learning-rules.md`.

Revise sem editar, salvo pedido explícito. Examine primeiro o diff e depois o contexto necessário. Priorize bugs, regressões, autenticação/autorização, validação, transações, contratos, migrations e testes; evite comentários apenas estéticos já cobertos pelas ferramentas.

Para cada achado, informe severidade, arquivo/local, cenário de falha e correção sugerida. Diferencie problemas confirmados de perguntas. Se não houver achados, diga isso e registre riscos ou verificações que não puderam ser executadas.
