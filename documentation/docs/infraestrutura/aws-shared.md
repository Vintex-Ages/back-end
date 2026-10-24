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
| Budget | vintex-monthly, teto US$35, toda a conta, alertas reais 28/30/35 e previsão 30 |
| Tags | Project=Vintex, Environment=staging, ManagedBy=Terraform |

O nome do módulo de rede ainda contém “shared” por reutilização do código.
A propriedade dos recursos é do state completo da staging. Produção e futuros
workflows OIDC/releases não estão implementados nesta entrega. Antes de reutilizar
esses recursos em produção, seu ciclo de vida deverá ser revisado; outro state
não deve tentar criá-los novamente.

## Operação

Na raiz do backend, com o perfil AWS institucional e
`infra/terraform/account.tfvars.json` preenchido (conta, nome do bucket e de 1 a
10 e-mails reais do Budget), o responsável aplica em duas etapas, revisando o
plano salvo antes de cada apply:

1. **`bootstrap`**: cria o bucket do state (privado, versionado, AES256, TLS
   obrigatório, `prevent_destroy`). O state inicial é local, porque o backend S3
   depende do bucket que ainda será criado; guarde backup privado do
   `terraform.tfstate` desse root.
2. **`aws`**: staging completa (rede, ECR, Budget e runtime AWS), no backend S3
   com a key `vintex/staging/terraform.tfstate`, criptografia e lock nativo.

Não é preciso criar bucket no console, e credenciais ficam apenas no perfil
local. Um state `vintex/shared/terraform.tfstate` antigo exige migração revisada:
nenhum import, combinação ou migração automática é executado.

Consulte o [README Terraform](https://github.com/Vintex-Ages/back-end/blob/develop/infra/terraform/README.md)
para a preparação e os comandos completos; e [AWS staging](./aws-staging.md) para
recursos/validação do ambiente e publicação da aplicação. A role EC2 não lê o
bucket de state.

## Verificação sem credenciais

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap test
terraform -chdir=infra/terraform/aws init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/aws validate
terraform -chdir=infra/terraform/aws test
```

O CI testa bucket, rede, ECR, Budget e integração com o runtime com provider
mockado e planos; não aplica recursos AWS. Confirmação de IAM, Budget real, SSM e
boot depende do responsável na conta institucional. As restrições IAM/SCP
continuam valendo.
