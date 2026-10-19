# Terraform — ambiente local e base AWS compartilhada

```
infra/terraform/
├── modules/
│   ├── network/       # VPC, subnets, rota de saída e security groups (VE-14)
│   ├── ecs_execution_role/ # papel mínimo de execução ECS (VE-14)
│   ├── media_storage/ # bucket privado e prefixos de mídia (VE-16)
│   ├── ai_messaging/  # fila de análise de imagens e DLQ (VE-17)
│   ├── shared_network/ # rede pública EC2 da AWS real (#272)
│   ├── container_registry/ # dois ECRs imutáveis, scan e retenção (#272)
│   └── project_budget/ # Budget mensal da conta dedicada (#272)
└── envs/
    ├── local/        # provider -> LocalStack/MiniStack, testes mockados
    └── shared/       # provider AWS real, state S3, testes mockados (#272)
```

Nenhum alvo do `Makefile` da raiz executa `terraform apply`. `make infra-qa` roda `fmt -check`, `init` e `validate`; `make infra-local-test` roda `terraform test` (mockado, via `mock_provider`, sem tocar LocalStack/MiniStack nem AWS real).

## AWS real: shared (#272)

Provider em `us-east-2`, restrito à conta informada, sem credenciais fixas ou
endpoints de emuladores. Cria VPC dedicada, uma subnet pública, Internet
Gateway/rota, ECRs `vintex-backend` e `freellmapi` e Budget de US$35/mês com os
quatro alertas da arquitetura. Mantém Terraform >=1.16 e AWS provider ~>6.66.0.

A conta pode estar vazia. O responsável primeiro configura SSO/MFA e cria
manualmente o bucket de state privado, versionado e criptografado em Ohio.
O backend usa `vintex/shared/terraform.tfstate` e lock nativo S3, sem DynamoDB.
Copie os arquivos `.example` do shared para `backend.tfbackend` e
`terraform.tfvars`, ambos ignorados pelo Git, e forneça conta, bucket e e-mails.

Validação **sem credenciais AWS ou backend real**:

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/envs/shared init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/envs/shared validate
terraform -chdir=infra/terraform/envs/shared test
```

Provisionamento **manual pelo responsável**, após bootstrap e revisão do PR:

```bash
export AWS_PROFILE=vintex
aws sso login --profile vintex
aws sts get-caller-identity
terraform -chdir=infra/terraform/envs/shared init -input=false -backend-config=backend.tfbackend
terraform -chdir=infra/terraform/envs/shared plan -out=shared.tfplan
terraform -chdir=infra/terraform/envs/shared show shared.tfplan
terraform -chdir=infra/terraform/envs/shared apply shared.tfplan
terraform -chdir=infra/terraform/envs/shared output
```

Outputs: `account_id`, `aws_region`, `vpc_id`, `public_subnet_id`,
`ecr_repositories` (nome/ARN/URL) e `budget` (nome/ARN). O roteiro completo
partindo de conta vazia está em
[Base AWS compartilhada](../../documentation/docs/infraestrutura/aws-shared.md).
Use checkout separado para testes offline se já inicializou este diretório
com backend real; antes do apply, inicialize sempre o backend S3 real.

O job `Terraform Validation` valida e testa `local` e `shared`, apenas com
providers mockados, sem credenciais AWS. Nenhum alvo Make ou job faz apply real.
Staging/runtime seguem #273 e #274 do épico #180, uma entrega por vez.

## Ambiente local

O ambiente `local` liga o provider EC2 ao MiniStack e IAM ao LocalStack. O
módulo de rede é descrito em [modules/README.md](modules/README.md). O plano
mockado verifica a composição e os contratos de saída sem criar VPC, role ou
outros recursos nos emuladores; os scripts de smoke test continuam usando
recursos sintéticos separados. Não executar `terraform apply` nesta fase.

A VE-16 acrescenta um bucket privado de mídia (`vintex-local-media`) com
bloqueio de acesso público e criptografia AES256. O módulo declara os prefixos
lógicos `products/photos/`, `products/videos/` e `payments/receipts/`; não cria
objetos vazios para simular pastas no S3. O plano mockado verifica bucket,
prefixos e bloqueio público. O script local provisiona o mesmo contrato no
LocalStack durante `make infra-up`; a composição Terraform continua sem `apply`.
