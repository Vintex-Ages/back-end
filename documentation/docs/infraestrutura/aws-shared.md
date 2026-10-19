---
sidebar_position: 6
---

# Base AWS compartilhada para staging manual (#272)

Próxima entrega: [runtime e deploy manual da staging (#273)](./aws-staging-runtime.md).

A [#272](https://github.com/Vintex-Ages/back-end/issues/272), parte do
[épico #180](https://github.com/Vintex-Ages/back-end/issues/180), prepara a
base compartilhada em `infra/terraform/aws`, selecionada por `config/shared.tfvars`.
A conta pode começar vazia: o novo root `bootstrap` cria o bucket de state
antes do shared, com execução manual pelo responsável. A implementação é validada sem credenciais,
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
O security group da staging está na [#274](./aws-staging.md), sem ingress. Não são criados
NAT Gateway, EC2, banco, CloudFront, recursos de produção, bucket de releases
ou roles/workflows de deploy nesta etapa.

## Preparação manual de uma conta vazia

Use o perfil já autorizado na subconta da faculdade, sem provisionar outra
conta ou alterar a governança institucional. O roteiro completo está no
[README do Terraform](https://github.com/Vintex-Ages/back-end/blob/develop/infra/terraform/README.md).

Na raiz do backend, instale Terraform >=1.16, AWS CLI v2, Python >=3.12 e Make:

```bash
export AWS_PROFILE=vintex-terraform
aws sts get-caller-identity
cp infra/terraform/account.tfvars.json.example infra/terraform/account.tfvars.json
chmod 600 infra/terraform/account.tfvars.json
```

Preencha uma única vez o ID confirmado pelo STS, nome único do bucket e
1–10 e-mails reais do Budget. Nenhuma credencial entra no arquivo ou na imagem.
SSO é usado se já fizer parte do perfil institucional; não é pré-requisito de
código para usar a identidade IAM autorizada. PowerUserAccess sozinho não cria
roles IAM: o responsável precisa das concessões para os recursos previstos.

## Configuração e primeiro apply manual

```bash
make terraform-init ENV=bootstrap
make terraform-plan ENV=bootstrap
make terraform-show ENV=bootstrap
make terraform-apply ENV=bootstrap

make terraform-init ENV=shared
make terraform-plan ENV=shared
make terraform-show ENV=shared
make terraform-apply ENV=shared
make terraform-output ENV=shared
```

Bootstrap cria o bucket privado/versionado/AES256/TLS-only, com ACLs desativadas
e proteção contra destruição; seu state é **local** em
`infra/terraform/.terraform/bootstrap/bootstrap.tfstate`. Guarde cópia privada.
Não há dependência de bucket pré-criado na conta vazia.
Shared usa `vintex/shared/terraform.tfstate` nesse bucket, com criptografia e
lock nativo S3. O backend e o provider restringem a conta esperada em Ohio.
O runner usa planos e diretórios de dados separados por ambiente e exige
confirmação antes do apply; alterações de configuração exigem novo plano.

Revise os dois ECRs, a rede e os quatro alertas antes de aplicar. Não publique
state/plan, que podem conter dados sensíveis. A role da EC2 não acessa state.
A identidade do operador precisa de S3 List/Get/Put para os states e Get/Put/Delete
para seus `.tflock`, além de administrar os recursos declarados.

## Outputs e sequência

| Output | Consumidor |
| --- | --- |
| `account_id`, `aws_region` | Conferência da conta/região |
| `vpc_id`, `public_subnet_id` | Ambiente staging #274 e futura produção |
| `ecr_repositories` | Mapa dos nomes para nome/ARN/URL, build manual e runtime #273 |
| `budget` | Nome/ARN do orçamento, conferência no console |

#272, #273 e #274 já têm implementação integrada à develop. A consolidação
completa o caminho de conta vazia até o apply manual, sem implantar aplicações.
Staging lê a rede diretamente do state shared; não copie IDs para tfvars.
Os futuros workflows OIDC/releases continuam no vintex-prod.

Os módulos locais de ECS/VPC Link são preservados. A nova rede EC2 usa
`shared_network`; o provider real não reutiliza endpoints ou credenciais
fictícias do ambiente local. Templates de PR e regras de promoção não mudam.

## Verificações sem conta AWS

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/aws init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/aws validate
terraform -chdir=infra/terraform/aws test
```

Os testes usam exclusivamente `mock_provider "aws"` e `command=plan`, com
conta/e-mails fictícios. Verificam rede/outputs, imutabilidade e retenção ECR,
orçamento/notificações e recusa de inputs inválidos. Os testes Python verificam
o provider, tags e backend, pois o mock não exerce autenticação nem conexão S3.
O job **Terraform Validation** faz o mesmo para `envs/local`, `bootstrap` e `aws`, sem OIDC ou
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
