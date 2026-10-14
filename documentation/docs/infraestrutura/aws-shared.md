---
sidebar_position: 6
---

# Base AWS compartilhada para staging manual (#272)

A [#272](https://github.com/Vintex-Ages/back-end/issues/272), parte do
[épico #180](https://github.com/Vintex-Ages/back-end/issues/180), prepara a
base compartilhada em `infra/terraform/envs/shared`. A conta pode começar
inteiramente vazia. O responsável configura o acesso e cria o bucket de state
antes do primeiro uso do Terraform. A implementação é validada sem credenciais,
com planos mockados; nenhum recurso AWS é provisionado pelos testes ou pelo CI.

## O que o shared cria

| Recurso | Configuração |
| --- | --- |
| VPC | `10.80.0.0/16`, DNS e hostnames habilitados |
| Subnet pública | `10.80.1.0/24`, `us-east-2a`, IP público automático |
| Saída | Internet Gateway, rota `0.0.0.0/0`, associação da subnet |
| ECR | `vintex-backend` e `freellmapi`, privados, tags imutáveis, scan no push, AES256 |
| Retenção ECR | Dez imagens mais recentes por repositório; `force_delete=false` |
| Budget | `vintex-monthly`, COST/MONTHLY/USD, teto US$35, toda a conta dedicada |
| Alertas | Real acima de US$28, US$30 e US$35; previsão acima de US$30 |
| Tags | `Project=Vintex`, `Environment=shared`, `ManagedBy=Terraform` |

O Budget acompanha a conta inteira, incluindo custos sem tags. Destinatários
AGES III/IV são fornecidos por variável local. O alerta não interrompe recursos
automaticamente; ao receber US$30, revisar a margem, e ao receber US$35,
desligar a staging manualmente conforme a especificação.

Subnet pública significa saída por Internet Gateway, não liberação de entrada.
O security group da staging será criado na #274, sem ingress. Não são criados
NAT Gateway, EC2, banco, CloudFront, recursos de produção, bucket de releases
ou roles/workflows de deploy nesta etapa.

## Preparação manual de uma conta vazia

Executada **pelo responsável na conta do projeto**, antes do `init` real:

1. Proteger o root com MFA e configurar IAM Identity Center com acesso federado
   e MFA para o responsável. A sessão precisa de permissões para criar a rede,
   ECR, Budget e administrar o state nesta conta dedicada.
2. Instalar AWS CLI v2 e Terraform >=1.16. Usar SSO, sem access keys permanentes:

   ```bash
   aws configure sso --profile vintex
   aws sso login --profile vintex
   export AWS_PROFILE=vintex
   aws sts get-caller-identity
   ```

3. Conferir o ID retornado e criar **manualmente no console S3**, em Ohio
   (`us-east-2`), um bucket de state com nome globalmente único, por exemplo
   `vintex-terraform-state-<ID-DA-CONTA>`. Ele fica fora do state que armazena.
   Habilitar versionamento, criptografia padrão SSE-S3/AES256, Object Ownership
   com ACLs desabilitadas e todos os bloqueios de acesso público. Não usar
   Object Lock: o lock nativo do Terraform é um objeto `.tflock` removível.
4. Conferir as permissões S3 do responsável: listar o bucket, ler/gravar
   `vintex/shared/terraform.tfstate` e ler/gravar/apagar
   `vintex/shared/terraform.tfstate.tflock`. Não é necessário DynamoDB.

Apenas o bucket e a configuração de acesso precisam existir antes do Terraform.
O Budget, a VPC e os ECRs são criados pelo próprio shared. Dados reais ficam
nos arquivos ignorados abaixo; não gravar chaves AWS em nenhum deles.

## Configuração e primeiro apply manual

Na raiz do backend:

```bash
cp infra/terraform/envs/shared/backend.tfbackend.example infra/terraform/envs/shared/backend.tfbackend
cp infra/terraform/envs/shared/terraform.tfvars.example infra/terraform/envs/shared/terraform.tfvars
```

Editar localmente:

- `backend.tfbackend`: nome do bucket real e `allowed_account_ids` com o ID
  confirmado pelo STS. A chave do state é `vintex/shared/terraform.tfstate`,
  região Ohio, criptografia e `use_lockfile=true` já estão fixados no backend.
- `terraform.tfvars`: o mesmo ID em `expected_account_id` e de 1 a 10 e-mails
  reais em `budget_email_addresses`. Os valores de exemplo são fictícios.

O backend e o provider restringem a conta. Com a sessão SSO ativa, o responsável
executa e revisa o plano antes de aplicar:

```bash
terraform -chdir=infra/terraform/envs/shared init -input=false -backend-config=backend.tfbackend
terraform -chdir=infra/terraform/envs/shared plan -out=shared.tfplan
terraform -chdir=infra/terraform/envs/shared show shared.tfplan
terraform -chdir=infra/terraform/envs/shared apply shared.tfplan
terraform -chdir=infra/terraform/envs/shared output
```

O plano salvo é ignorado pelo Git. Confirmar a conta, os dois ECRs, a rede e os
quatro alertas. Se a conta/região estiver errada ou o plano incluir recursos
inesperados, corrigir a configuração local e gerar um novo plano antes do apply.
Não executar destroy para desfazer uma implantação da aplicação.

## Outputs e sequência

| Output | Consumidor |
| --- | --- |
| `account_id`, `aws_region` | Conferência da conta/região |
| `vpc_id`, `public_subnet_id` | Ambiente staging #274 e futura produção |
| `ecr_repositories` | Mapa dos nomes para nome/ARN/URL, build manual e runtime #273 |
| `budget` | Nome/ARN do orçamento, conferência no console |

A #169 foi incorporada pela PR #282. Após revisão e merge da #272, segue a
#273 (runtime de cinco serviços e deploy manual); depois a #274 (EC2 e recursos
próprios da staging). A aplicação e seu banco ainda não são implantados pela
#272. State de staging/produção terá chave separada, nunca reutilizando shared.
Os futuros workflows com OIDC e releases pertencem ao vintex-prod.

Os módulos locais de ECS/VPC Link são preservados. A nova rede EC2 usa
`shared_network`; o provider real não reutiliza endpoints ou credenciais
fictícias do ambiente local. Templates de PR e regras de promoção não mudam.

## Verificações sem conta AWS

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/envs/shared init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/envs/shared validate
terraform -chdir=infra/terraform/envs/shared test
```

Os testes usam exclusivamente `mock_provider "aws"` e `command=plan`, com
conta/e-mails fictícios. Verificam rede/outputs, imutabilidade e retenção ECR,
orçamento/notificações e recusa de inputs inválidos. Os testes Python verificam
o provider, tags e backend, pois o mock não exerce autenticação nem conexão S3.
O job **Terraform Validation** faz o mesmo para `local` e `shared`, sem OIDC ou
credenciais AWS. Dependências dos providers são baixadas do registry no init.

Use um checkout separado para testar offline se este diretório já foi
inicializado com backend real. Antes de um apply, inicialize o backend real;
`init -backend=false` é somente o caminho de validação, não de provisionamento.

Após o apply manual, conferir no console: VPC/subnet/rota, ECRs com scan e tags
imutáveis, quatro notificações do Budget e state versionado no bucket. Esses
testes operacionais dependem da sessão/conta do responsável e não foram feitos
pelos testes mockados.

## Referências

- [Backend S3 e permissões para lock nativo](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Terraform test](https://developer.hashicorp.com/terraform/cli/commands/test)
- [ECR no AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository)
- [Budget no AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/budgets_budget)
