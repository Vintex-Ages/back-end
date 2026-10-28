# Terraform Vintex — staging completa

A infraestrutura AWS é provisionada pelo responsável na raiz do **back-end**.
A conta institucional pode começar vazia. O Terraform cria também o bucket de
state; não é necessário criá-lo no console. Todos os serviços regionais ficam
em **us-east-2 (Ohio)**, conforme AGES. Produção não está implementada aqui.

## Preparar uma vez

Ferramentas: Terraform >=1.16 (CI: 1.16.4), Python >=3.12, Make, AWS CLI v2 e
boto3 na versão de `requirements.txt` (1.43.64). Use um venv Python ativado para
instalar o SDK; o runner usa `python3` do ambiente ativo. O deploy da aplicação
requer também as ferramentas do [runtime manual](../../documentation/docs/infraestrutura/aws-staging-runtime.md).

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install boto3==1.43.64
export AWS_PROFILE=vintex-terraform
aws sts get-caller-identity
cp infra/terraform/account.tfvars.json.example infra/terraform/account.tfvars.json
chmod 600 infra/terraform/account.tfvars.json
```

Não sobrescreva `account.tfvars.json` se já estiver preenchido. Informe somente:

- `expected_account_id`: os 12 dígitos da conta confirmada pelo STS.
- `state_bucket`: nome S3 globalmente único, como `vintex-terraform-state-<CONTA>`.
- `budget_email_addresses`: de 1 a 10 e-mails reais dos responsáveis pelo Budget.
- `enable_budget` (opcional, padrão `true`): defina `false` se a política da conta
  (SCP) não permitir criar Budgets; nesse caso `budget_email_addresses` pode ficar
  vazia e o Budget não é criado. Com `true`, os e-mails continuam obrigatórios.
- `public_preview` (opcional, padrão `false`): abre a staging ao público enquanto a
  instância está de pé (IP elástico e porta 80 só para o CloudFront). Desligado, a
  staging continua sem ingress e acessível apenas por SSM.

Use a identidade já autorizada na subconta da faculdade. SSO só é necessário
se seu perfil institucional usa SSO; nesse caso renove com `aws sso login`.
Credenciais IAM ficam no perfil AWS local, nunca neste arquivo ou na imagem.
O operador precisa das concessões institucionais para S3, EC2/VPC, ECR, IAM e
PassRole, Budgets, SQS, SSM, CloudWatch Logs e Scheduler. PowerUserAccess sozinho
não cria roles IAM. O código não contorna IAM/SCP nem configura outra conta.

## Executar a infraestrutura

```bash
make terraform-validate staging
make infra-deploy staging
```

O primeiro comando inicializa somente o cache de validação, com backend
**desativado**. Não precisa de conta, boto3 ou credenciais; pode baixar providers
públicos. Execute também `make terraform-test staging` para os planos mockados.

O segundo comando valida os dois roots sem backend, verifica conta, região e
states legados, e conduz:

1. **Bucket administrativo:** init/plan/show/apply do root `bootstrap`. O state
   inicial é local porque o backend S3 depende do bucket que ainda será criado.
2. **Staging completa:** init/plan/show/apply do root `aws`, incluindo rede,
   dois ECRs, Budget, EC2/role, mídia, filas/DLQ, parâmetros, logs e Scheduler.
3. Exibição dos outputs necessários para publicar a aplicação.

Cada apply pede que você digite o ambiente indicado (`bootstrap` ou `staging`)
depois da apresentação do plano. Não existe auto-approve, retry automático,
apply em validação ou provisionamento no CI. Até planos sem mudanças são
apresentados para revisão. As execuções seguintes revisam as mesmas duas
configurações e reutilizam os recursos existentes; não recriam o bucket.

O Make aceita somente um comando e um ambiente por chamada. Sem ambiente,
validação/testes usam `local`; comandos de provisionamento exigem seleção AWS
explícita. `ENV` e `TF_ENV` do shell não selecionam o destino. Erros de digitação
são recusados antes de executar Terraform. Os agregadores `infra-qa`,
`infra-local-test` e `infra-complete` continuam exclusivamente locais.

## State, planos e retomada

| Local | Finalidade |
| --- | --- |
| `bootstrap/` | Terraform que cria/protege o bucket administrativo |
| `aws/` + `config/staging.tfvars` | Toda a infraestrutura da staging, sem state shared |
| `state/bootstrap/terraform.tfstate` e `identity.json` | State persistente do bucket e identificação da conta/backend |
| `state/staging-layout.json` | Identificação que permite retomar o primeiro apply parcial |
| `.terraform/bootstrap/` e `.terraform/staging/` | Cache operacional e planos revisados |
| `.terraform/qa/{local,bootstrap,staging}/` | Cache de validação isolado da operação |
| S3 `vintex/staging/terraform.tfstate` | State completo da staging, criptografado e com lock nativo |

`state/`, arquivo da conta, planos e caches são privados e excluídos de Git e
Docker. **Guarde backup privado do diretório `state/`**, inclusive da identificação
do bootstrap; ele não é cache. Limpar `.terraform/` não apaga esse registro.
O bucket tem versionamento, AES256, ACLs desativadas, bloqueio público,
TLS obrigatório, `prevent_destroy` e `force_destroy=false`. A role EC2 não lê state.

O runner exige workspace `default`, recusa `TF_CLI_ARGS*`, isola os planos e
confere conta/configuração/fontes/integridade antes do apply e novamente após
a confirmação. Um apply falho invalida seu plano; não é permitido reutilizá-lo.
O lock local impede duas operações no mesmo checkout; o lock S3 protege o state
remoto. Use um único responsável para operar o bootstrap local.

Se uma etapa falhar, a próxima não começa. Leia o erro do Terraform e a orientação
do runner, corrija a causa e execute novamente `make infra-deploy staging`.
Novos planos consultam o state preservado e mostram o que falta. Sessão expirada
exige renovar o perfil; AccessDenied exige conferir as concessões institucionais;
não desative as proteções para prosseguir. Segredos e payloads SDK não são impressos.

Bucket existente sem o state local do bootstrap exige restauração do backup ou
adoção manual revisada. State bootstrap no caminho antigo `.terraform/` e states
AWS separados de shared/staging exigem migração revisada. O runner **não combina
states, importa recursos nem move state automaticamente**. Não aplique esta
consolidação sobre a estrutura antiga já provisionada usando comandos nativos.

## Terraform direto e comandos granulares

Make é uma conveniência. Os comandos protegidos continuam disponíveis:

```bash
make terraform-init staging
make terraform-plan staging
make terraform-show staging
make terraform-apply staging
make terraform-output staging
```

Eles pressupõem o bucket preparado. Para operação manual sem Make, o equivalente
nativo da primeira fase é (paths relativos à raiz do backend):

```bash
mkdir -p infra/terraform/state/bootstrap
chmod 700 infra/terraform/state infra/terraform/state/bootstrap
export TF_DATA_DIR="$PWD/infra/terraform/.terraform/bootstrap/data"
terraform -chdir=infra/terraform/bootstrap init -lockfile=readonly \
  -backend-config="path=$PWD/infra/terraform/state/bootstrap/terraform.tfstate"
terraform -chdir=infra/terraform/bootstrap plan \
  -var-file=../account.tfvars.json -out="$TF_DATA_DIR/bootstrap.tfplan"
terraform -chdir=infra/terraform/bootstrap show "$TF_DATA_DIR/bootstrap.tfplan"
terraform -chdir=infra/terraform/bootstrap apply "$TF_DATA_DIR/bootstrap.tfplan"
```

Para a staging, inicialize `aws/` com backend S3 (bucket da conta, key
`vintex/staging/terraform.tfstate`, region `us-east-2`, encrypt/use_lockfile true,
allowed_account_ids da conta) e use `-var-file=../account.tfvars.json` junto de
`-var-file=../config/staging.tfvars` no plan. Preserve os planos e revise-os antes
de aplicar. O backend é configurado no init; variáveis de recursos entram no plan.
Os comandos nativos não executam as verificações adicionais de identidade,
layout e integridade do runner. Não alterne os dois procedimentos no mesmo
checkout: operação iniciada nativamente exige reconciliação revisada da
identificação local antes de usar `infra-deploy`.

## Depois da infraestrutura: aplicação

Confirme bucket versionado, rede/ECR/Budget, EC2 Online no SSM, marker
`bootstrap-ready`, Docker, guard IMDS, cinco grupos de logs e três schedules.
Siga [AWS staging](../../documentation/docs/infraestrutura/aws-staging.md) e o
[runtime manual](../../documentation/docs/infraestrutura/aws-staging-runtime.md)
para publicar imagens ARM64 e frontend, preencher parâmetros, aplicar migrations
e subir Nginx/API/worker/FreeLLMAPI/Postgres pelo script existente na EC2.
O Terraform não publica aplicações e este PR não cria um pipeline de deploy.

O banco continua Postgres 16 + pgvector no Compose, em `db:5432`. A chave IA é
opcional no primeiro deploy e inserida apenas no Parameter Store; sua ausência
não impede API/health. Os demais segredos obrigatórios devem ser preenchidos.

## Verificações sem AWS

```bash
make terraform-fmt
make terraform-validate local
make terraform-test local
make terraform-validate bootstrap
make terraform-test bootstrap
make terraform-validate staging
make terraform-test staging
pytest tests/test_terraform_env.py tests/test_terraform_make.py tests/test_infra_shared_config.py tests/test_infra_staging_config.py -v
```

CI usa esses mesmos alvos nos três roots, sem credenciais ou apply. Testes
Terraform são exclusivamente planos com provider mockado; testes Python usam
clientes AWS/comandos simulados. O contrato real do Make roda no checkout do CI;
a imagem da API não precisa de Make/Terraform para funcionar. Os testes locais
não comprovam permissões reais, disponibilidade ARM64, boot/SSM ou faturamento.

## Referências

- [Backend S3 e bucket preexistente](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Backend local](https://developer.hashicorp.com/terraform/language/backend/local)
- [Terraform CLI](https://developer.hashicorp.com/terraform/cli/commands)
