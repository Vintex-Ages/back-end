# Terraform Vintex — local e AWS staging

## Organização

```text
infra/terraform/
├── bootstrap/              # bucket de state, backend local
├── aws/                    # um root AWS: shared OU staging
├── config/
│   ├── shared.tfvars       # deployment = "shared"
│   └── staging.tfvars      # deployment = "staging"
├── account.tfvars.json.example
├── envs/local/             # emuladores, preservado
└── modules/                # recursos reutilizados, sem duplicação por ambiente
```

Todos os serviços regionais AWS ficam em **us-east-2 (Ohio)**, conforme AGES.
`infra/vintex-infra` é Docker Compose local; não é a pasta de apply AWS.
A configuração AWS é reutilizada com `-var-file`; os backends continuam separados.
Workspaces não selecionam componentes: usamos sempre `default`.

| ENV | Root | State | Cria |
| --- | --- | --- | --- |
| `local` (default) | `envs/local` | local de desenvolvimento | somente planos mockados de emuladores |
| `bootstrap` | `bootstrap` | `.terraform/bootstrap/bootstrap.tfstate` local | bucket administrativo do state |
| `shared` | `aws` + `config/shared.tfvars` | S3 `vintex/shared/terraform.tfstate` | VPC/subnet/IGW/rota, 2 ECRs, Budget |
| `staging` | `aws` + `config/staging.tfvars` | S3 `vintex/staging/terraform.tfstate` | EC2/role, mídia, SQS/DLQ, parâmetros, logs, Scheduler |

Bootstrap precisa de backend local porque o bucket ainda não existe. Ele cria
um bucket privado, versionado, AES256, ACLs desabilitadas e policy que nega HTTP.
`prevent_destroy` e `force_destroy=false` protegem o bucket. Guarde uma cópia
privada do state de bootstrap após apply; não o apague nem o anexe ao Git/PR.
O backend S3 dos demais usa criptografia, lock nativo e restrição de conta,
sem DynamoDB. A role da EC2 não recebe acesso ao state.

## Conta institucional vazia: preparação única

Na raiz do **back-end**, com Terraform >=1.16 (CI: 1.16.4), Python >=3.12,
Make e AWS CLI v2 instalados:

```bash
export AWS_PROFILE=vintex-terraform
aws sts get-caller-identity
cp infra/terraform/account.tfvars.json.example infra/terraform/account.tfvars.json
chmod 600 infra/terraform/account.tfvars.json
```

Use o perfil já autorizado na subconta da faculdade. Se ele usa SSO, faça
`aws sso login --profile vintex-terraform`; se usa IAM, as credenciais ficam
somente no perfil local do AWS CLI. Não é necessário criar outra conta,
Identity Center ou bucket manualmente. Restrições/SCP da instituição continuam
valendo: o código não concede permissões ao operador.

Edite **apenas** `account.tfvars.json` com:

- `expected_account_id`: ID confirmado pelo STS, 12 dígitos.
- `state_bucket`: nome globalmente único, por exemplo `vintex-terraform-state-<CONTA>`.
- `budget_email_addresses`: de 1 a 10 destinatários reais dos alertas (obrigatórios no shared).

Não coloque chaves AWS nem segredos da aplicação nesse arquivo. Ele e os arquivos
em `.terraform/` são ignorados no Git e excluídos do contexto Docker. A região é
fixa no código; o operador não precisa repeti-la em cada ambiente.

A identidade do operador precisa administrar os recursos declarados: S3 do
state e mídia, VPC/EC2, ECR, Budget, IAM roles/profiles/policies e PassRole,
SQS, parâmetros SSM, logs CloudWatch e Scheduler. PowerUserAccess sozinho não
permite criar as roles IAM. Use as concessões já aprovadas pela faculdade;
se houver AccessDenied, solicite a ação específica, sem ampliar o escopo.
SSM Session Manager e seu plugin local serão necessários para acessar a staging.

## Provisionar em ordem — execução manual

```bash
make terraform-init ENV=bootstrap
make terraform-plan ENV=bootstrap
make terraform-show ENV=bootstrap
make terraform-apply ENV=bootstrap
make terraform-output ENV=bootstrap

make terraform-init ENV=shared
make terraform-plan ENV=shared
make terraform-show ENV=shared
make terraform-apply ENV=shared
make terraform-output ENV=shared

make terraform-init ENV=staging
make terraform-plan ENV=staging
make terraform-show ENV=staging
make terraform-apply ENV=staging
make terraform-output ENV=staging
```

O apply pede que você digite o ambiente. Ele aplica somente o plano salvo para
esse ambiente; mudanças de conta, configuração, módulos ou arquivo do plano
exigem novo plan. Apply parcial/falho também exige novo plan. Não há apply
implícito em init, validate, test ou CI. `ENV=local` não permite apply.
Não use `TF_CLI_ARGS*` nem outro `TF_WORKSPACE` com estes comandos.

O runner `scripts/infra/terraform_env.py` gera o backend a partir do único arquivo
de conta e usa `TF_DATA_DIR`/plano separados por ENV, com permissões privadas.
Não há wrapper que faça deploy de aplicações neste fluxo.
A seleção shared/staging nativa é equivalente a:

```bash
# Exemplo após make terraform-init ENV=staging, na raiz do backend:
TF_DATA_DIR="$PWD/infra/terraform/.terraform/staging/data" \
terraform -chdir=infra/terraform/aws plan \
  -var-file=../account.tfvars.json -var-file=../config/staging.tfvars
```

Use o Make para manter a revisão e a validação do plano salvo. O backend não
aceita variáveis Terraform, por isso seus dados são passados no init por
`-backend-config`, enquanto `-var-file` seleciona a composição dos recursos.

Staging lê `vpc_id`, `public_subnet_id`, conta e região do state shared; não copie
IDs manualmente. O plano recusa shared de outra conta/região ou rede de outro
projeto/sem IPv4 automático. Shared não tenta ler um state preexistente.

## Validar infraestrutura e publicar aplicação

Depois dos applies, confirme state versionado, Budget com 4 alertas, ECRs, rede,
instância Online no SSM, 5 grupos de logs e os 3 schedules de Brasília.
Confira na EC2 o marker `bootstrap-ready`, Docker e o guard IMDS.
Siga [AWS staging](../../documentation/docs/infraestrutura/aws-staging.md) para
os comandos e [runtime manual](../../documentation/docs/infraestrutura/aws-staging-runtime.md)
para imagens ARM64, frontend, parâmetros, migrations, deploy e túnel SSM.
Terraform não publica front/backend e não preenche segredos reais.
O banco permanece Postgres 16 + pgvector no Compose (`db:5432`).
A chave da IA pode ser inserida depois, somente no Parameter Store da AWS;
sua ausência não bloqueia API/health nem o provisionamento.

## Migração de configurações anteriores

`envs/shared` e `envs/staging` foram consolidados em `aws`. Não inicialize as
pastas antigas. Para uma conta ainda vazia, siga bootstrap → shared → staging.

Se já existe state, preserve **o mesmo bucket, conta e keys**. Faça backup
privado de cada state antes de migrar. Os blocos `moved` mapeiam os módulos
anteriores para `[0]` em cada state, sem combinar states. Revise o plano:
a consolidação não deve destruir/recriar recursos. Não aplique um plano que
proponha isso. Bucket administrativo que já existe fora do Terraform deve ser
importado no bootstrap com seus recursos de configuração, em manutenção
revisada; não tente criá-lo novamente. Alterações operacionais no state exigem
análise do responsável e não são executadas automaticamente pelo runner.

## Verificações sem credenciais AWS

Em checkout de desenvolvimento (não no diretório de operação):

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap test
terraform -chdir=infra/terraform/aws init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/aws validate
terraform -chdir=infra/terraform/aws test
pytest tests/test_terraform_env.py tests/test_infra_shared_config.py tests/test_infra_staging_config.py -v
```

Tests Terraform usam mock_provider e somente plan; bootstrap também é mockado.
CI valida os roots local/bootstrap/aws, sem credenciais ou apply.
Init pode baixar providers públicos. Isso não provisiona recursos AWS.
O isolamento do backend e a recusa de planos errados são testados com subprocess
mockado; somente um apply e validação reais pelo responsável comprovam operação.

## Desenvolvimento local

`make terraform-init`, `make terraform-validate`, `make terraform-test`,
`make infra-qa` e `make infra-complete` mantêm `ENV=local` como default.
LocalStack (S3/SQS/Secrets/IAM/STS) e MiniStack (ECS/Cloud Map/API Gateway/ECR)
são recursos sintéticos independentes da conta AWS. Não use apply AWS para
subir esses emuladores. Não há migração do state local para AWS.

## Referências

- [Backend parcial e init](https://developer.hashicorp.com/terraform/language/backend)
- [Backend S3 e lock nativo](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Arquivos de variáveis](https://developer.hashicorp.com/terraform/language/values/variables)
- [Módulos moved](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring)
