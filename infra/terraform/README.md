# Terraform Vintex — staging completa

A infraestrutura AWS é provisionada pelo responsável na raiz do **back-end**.
A conta institucional pode começar vazia. O Terraform cria também o bucket de
state; não é necessário criá-lo no console. Todos os serviços regionais ficam
em **us-east-2 (Ohio)**, conforme AGES. Produção não está implementada aqui.

```
infra/terraform/
├── bootstrap/                  # bucket do state (state local, prevent_destroy)
├── aws/                        # staging completa, um único state
├── config/staging.tfvars       # perfil público do ambiente
├── account.tfvars.json.example # conta, bucket e e-mails do Budget (cópia privada)
├── modules/                    # módulos usados pelo aws/ (ver modules/README.md)
└── envs/
    └── local/                  # provider -> LocalStack/MiniStack, testes mockados
```

## Preparar uma vez

Ferramentas: Terraform >=1.16 (CI: 1.16.4) e AWS CLI v2. O deploy da aplicação
requer também as ferramentas do
[runtime manual](../../documentation/docs/infraestrutura/aws-staging-runtime.md).

```bash
export AWS_PROFILE=vintex-terraform
aws sts get-caller-identity
cp infra/terraform/account.tfvars.json.example infra/terraform/account.tfvars.json
chmod 600 infra/terraform/account.tfvars.json
```

Não sobrescreva `account.tfvars.json` se já estiver preenchido. Informe somente:

- `expected_account_id`: os 12 dígitos da conta confirmada pelo STS.
- `state_bucket`: nome S3 globalmente único, como `vintex-terraform-state-<CONTA>`.
- `budget_email_addresses`: de 1 a 10 e-mails reais dos responsáveis pelo Budget.

Use a identidade já autorizada na subconta da faculdade. SSO só é necessário
se seu perfil institucional usa SSO; nesse caso renove com `aws sso login`.
Credenciais IAM ficam no perfil AWS local, nunca neste arquivo ou na imagem.
O operador precisa das concessões institucionais para S3, EC2/VPC, ECR, IAM e
PassRole, Budgets, SQS, SSM, CloudWatch Logs e Scheduler. PowerUserAccess sozinho
não cria roles IAM. O código não contorna IAM/SCP nem configura outra conta.

## Executar a infraestrutura

Os comandos abaixo partem da raiz do backend. Revise cada plano antes do apply;
não use auto-approve. Planos (`*.tfplan`), states e o arquivo da conta são
privados e excluídos de Git e Docker.

### 1. Bootstrap: bucket do state

```bash
terraform -chdir=infra/terraform/bootstrap init -lockfile=readonly
terraform -chdir=infra/terraform/bootstrap plan -var-file=../account.tfvars.json -out=bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap show bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap apply bootstrap.tfplan
```

O state inicial é **local**, porque o backend S3 depende do bucket que este root
cria. Guarde um backup privado do `terraform.tfstate` do `bootstrap/`: ele é o
único registro do bucket. O bucket tem versionamento, AES256, ACLs desativadas,
bloqueio público, TLS obrigatório, `prevent_destroy` e `force_destroy = false`.

### 2. Staging completa

```bash
terraform -chdir=infra/terraform/aws init -lockfile=readonly \
  -backend-config="bucket=<BUCKET_DO_STATE>" \
  -backend-config="key=vintex/staging/terraform.tfstate" \
  -backend-config="region=us-east-2" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true" \
  -backend-config='allowed_account_ids=["<CONTA>"]'
terraform -chdir=infra/terraform/aws plan \
  -var-file=../account.tfvars.json -var-file=../config/staging.tfvars -out=staging.tfplan
terraform -chdir=infra/terraform/aws show staging.tfplan
terraform -chdir=infra/terraform/aws apply staging.tfplan
terraform -chdir=infra/terraform/aws output
```

O root `aws/` reúne rede, dois ECRs, Budget, EC2/role, mídia, filas/DLQ,
parâmetros, logs e Scheduler, com referências diretas entre módulos: não há
execução separada de `shared`, `remote_state` nem cópia de IDs. O backend é
configurado no `init`; as variáveis de recursos entram no `plan`. O state fica em
S3 (`vintex/staging/terraform.tfstate`), criptografado e com lock nativo; a role
da EC2 não lê state.

State e plano podem conter valores `SecureString` após o refresh, mesmo com
`ignore_changes`: não os anexe a issues, Git ou imagens. Se um apply falhar, leia
o erro do Terraform, corrija a causa e gere um novo plano sobre o state
preservado; não reutilize o plano que falhou. Sessão expirada exige renovar o
perfil, e `AccessDenied` exige conferir as concessões institucionais; não
desative proteções para prosseguir.

Esta composição substitui os antigos `envs/shared` e `envs/staging`. Nada foi
aplicado com aquela estrutura; se algum state `vintex/shared/terraform.tfstate`
existir, ele exige migração revisada (não há import, combinação nem migração
automática). Não aplique esta composição por cima da estrutura antiga já
provisionada.

## Depois da infraestrutura: aplicação

Confirme bucket versionado, rede/ECR/Budget, EC2 Online no SSM, marker
`bootstrap-ready`, Docker, guard IMDS, cinco grupos de logs e três schedules.
Siga [AWS staging](../../documentation/docs/infraestrutura/aws-staging.md) e o
[runtime manual](../../documentation/docs/infraestrutura/aws-staging-runtime.md)
para publicar imagens ARM64 e frontend, preencher parâmetros, aplicar migrations
e subir Nginx/API/worker/FreeLLMAPI/Postgres pelo script existente na EC2.
O Terraform não publica aplicações e esta composição não cria pipeline de deploy.

O banco continua Postgres 16 + pgvector no Compose, em `db:5432`. A chave IA é
opcional no primeiro deploy e inserida apenas no Parameter Store; sua ausência
não impede API/health. Os demais segredos obrigatórios devem ser preenchidos.

## Verificações sem AWS

```bash
terraform fmt -check -recursive infra/terraform
for dir in envs/local bootstrap aws; do
  terraform -chdir="infra/terraform/$dir" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="infra/terraform/$dir" validate
  terraform -chdir="infra/terraform/$dir" test
done
pytest tests/test_infra_shared_config.py tests/test_infra_staging_config.py -v
```

Use um checkout separado se algum desses diretórios já foi inicializado com
backend real. O CI repete esse laço nos três roots, sem credenciais ou apply.
Os testes Terraform usam provider mockado e `plan`; os testes Python leem os
arquivos `.tf`. Nada disso comprova permissões reais, disponibilidade ARM64,
boot/SSM ou faturamento.

## Referências

- [Backend S3 e bucket preexistente](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Backend local](https://developer.hashicorp.com/terraform/language/backend/local)
- [Terraform CLI](https://developer.hashicorp.com/terraform/cli/commands)
