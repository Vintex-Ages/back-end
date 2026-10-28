---
sidebar_position: 6
---

# Base AWS integrada à staging (#272 / #288)

A base da [#272](https://github.com/Vintex-Ages/back-end/issues/272), parte da
[#180](https://github.com/Vintex-Ages/back-end/issues/180), permanece implementada
pelos módulos `shared_network`, `container_registry` e `project_budget`.
A #288 reúne sua composição e a #274 no **mesmo root e state de staging**.
Não é mais necessário executar um ambiente `shared` separado nem copiar IDs.

## Recursos da base

| Recurso | Configuração |
| --- | --- |
| VPC/subnet | 10.80.0.0/16 e 10.80.1.0/24, DNS, us-east-2a e IPv4 automático |
| Saída | Internet Gateway, rota pública e associação da subnet |
| ECR | vintex-backend e freellmapi, privados, AES256, tags imutáveis e scan no push |
| Retenção ECR | Dez imagens; sem exclusão forçada |
| Budget | vintex-monthly, teto US$35, toda a conta, alertas reais 28/30/35 e previsão 30; opcional (`enable_budget`) |
| Tags | Project=Vintex, Environment=staging, ManagedBy=Terraform |

O nome do módulo de rede ainda contém “shared” por reutilização do código.
A propriedade dos recursos é do state completo da staging. Produção e futuros
workflows OIDC/releases não estão implementados nesta entrega. Antes de reutilizar
esses recursos em produção, seu ciclo de vida deverá ser revisado; outro state
não deve tentar criá-los novamente.

## Operação

Na raiz do backend, com perfil institucional e `account.tfvars.json` preenchido:

```bash
make terraform-validate staging
make infra-deploy staging
```

O comando de infraestrutura conduz a criação do bucket pelo Terraform e o plano
completo da staging, com revisão/confirmação antes de cada apply. Não é preciso
criar bucket no console. Conta, nome do bucket e 1–10 e-mails reais do Budget (ou
`enable_budget: false`, se a política da conta não permitir Budgets) são
configurados uma vez; credenciais ficam apenas no perfil local.

O state inicial do bucket fica em `infra/terraform/state/bootstrap/`, fora do
cache, com identidade persistente e backup privado obrigatório. O restante usa
S3 `vintex/staging/terraform.tfstate`, com criptografia e lock nativo. State
`vintex/shared/terraform.tfstate` antigo, bucket sem state local e bootstrap no
caminho antigo interrompem o fluxo para recuperação/migração revisada.
Nenhum import, combinação ou migração automática é executado.

Consulte o [README Terraform](https://github.com/Vintex-Ages/back-end/blob/develop/infra/terraform/README.md)
para preparação, ferramentas, comandos nativos e recuperação; e
[AWS staging](./aws-staging.md) para recursos/validação do ambiente e publicação
da aplicação. A role EC2 não lê o bucket de state.

## Verificação sem credenciais

```bash
make terraform-validate bootstrap
make terraform-test bootstrap
make terraform-validate staging
make terraform-test staging
```

O cache QA usa backend desativado e não lê a conta real. CI testa bucket, rede,
ECR, Budget e integração com o runtime com provider mockado e planos; não aplica
recursos AWS. Confirmação de IAM, Budget real, SSM e boot depende do responsável
na conta institucional. As restrições IAM/SCP continuam valendo.
