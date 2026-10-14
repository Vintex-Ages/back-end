---
title: Cognitrace
sidebar_position: 2
---

# Captura de uso de IA com Cognitrace

Cognitrace é uma extensão do VS Code que observa os arquivos locais de sessão
de assistentes compatíveis e registra prompts e respostas em `.ai_log/`, no
workspace. A captura fica habilitada neste repositório pelo arquivo
`.vscode/settings.json`; a extensão recomendada é
[`schardosim.cognitrace`](https://marketplace.visualstudio.com/items?itemName=schardosim.cognitrace).

## Arquivos gerados

O addon cria arquivos `prompt_log_YYYY-MM-DD_<git-username>.json`. Cada entrada
inclui timestamp, origem do assistente, branch, usuário Git, diretório de
trabalho, papel (`user`/`assistant`) e conteúdo da mensagem.

Esses registros podem conter contexto privado, segredos colados por engano,
caminhos locais e respostas longas. Por isso, `.ai_log/` é ignorado pelo Git e
os JSONs brutos não são publicados no Docusaurus. A extensão não envia esses
dados para um serviço remoto; a captura fica no disco local.

## Evidência pública

Para documentação compartilhada, a fonte é a seção **Onde foi utilizado IA?**
de cada PR mergeado. O inventário histórico em
[Uso de IA por PR](./uso-de-ia-por-pr) contém os 24 PRs mergeados encontrados
na revisão retroativa, com suas declarações públicas e links de origem.

O back-end não tinha `.ai_log/` nem setting Cognitrace antes desta integração,
então as conversas passadas não podem ser reconstruídas pelo addon. O PR #95
foi mantido como pendente de confirmação porque a seção contém apenas o texto
do template; isso não permite concluir se houve ou não uso de IA.

## Processo para novas mudanças

1. Instale a extensão Cognitrace recomendada e confirme que a captura está ativa para o workspace.
2. Continue preenchendo **Onde foi utilizado IA?** no PR com uma descrição revisada e apropriada para publicação.
3. Atualize o inventário por PR usando essa declaração pública; não copie os prompts ou as respostas de `.ai_log/` para o repositório.
