---
sidebar_position: 7
---

# Ambiente AWS real de staging (#274)

A [#274](https://github.com/Vintex-Ages/back-end/issues/274), parte do
[épico #180](https://github.com/Vintex-Ages/back-end/issues/180), conecta a
[base compartilhada #272](./aws-shared.md) ao
[runtime e deploy manual #273](./aws-staging-runtime.md).
O responsável executa bootstrap, apply e deploy com sessão temporária SSO.
**Os testes e o CI não provisionam recursos AWS.**

## Recursos e contratos

| Componente | Configuração |
| --- | --- |
| State | Mesmo bucket administrativo do shared, chave independente `vintex/staging/terraform.tfstate`, criptografia e lock nativo S3 |
| Provider | Ohio `us-east-2`, `allowed_account_ids`, sem endpoints locais ou access keys |
| EC2 | `t4g.small`, Amazon Linux 2023 ARM64, EBS gp3 criptografado de 10 GB e swap de 1 GiB |
| Rede | VPC/subnet recebidas do shared, IPv4 automático, nenhum ingress, saída TCP 443 |
| Metadados | IMDSv2 obrigatório, hop limit 2, IPv6 desativado; guard da #273 instalado antes do Docker |
| Mídia | `vintex-media-staging-<CONTA>`, privado, AES256, ACLs desativadas e HTTP negado |
| Mensageria | `vintex-ai-staging` e DLQ, SSE-SQS, polling 20 s, visibilidade 180 s, redrive após 3 entregas, DLQ 14 dias |
| Parâmetros | Seis SecureString Standard em `/vintex/staging/`, inicialmente provisórios |
| Logs | `/vintex/staging/{proxy,api,worker,freellmapi,db}`, retenção 7 dias |
| Horário | Brasília, seg–sex liga 10h/desliga 22h; varredura diária desliga 02h |

Tags: `Project=Vintex`, `Environment=staging`, `ManagedBy=Terraform`.
Não há Elastic IP, SSH, CloudFront, RDS, backup, pipeline ou recurso de produção.
O banco continua sendo **db:5432 do Compose**, com pgvector/Postgres 16 e migrations
existentes; Terraform não cria outro banco.

O módulo `ai_messaging` aceita os tempos da staging, preservando os defaults do
ambiente local. O bootstrap instala Docker, iptables-nft, Python 3.12/boto3 e
Compose ARM64 v5.6.0 com checksum fixado. Python 3.12 é explícito: o Python
padrão do Amazon Linux 2023 é 3.9. A instância usa créditos CPU Standard para
não gerar cobrança de surplus. O disco é descartado ao destruir a EC2.

O bootstrap não sobe aplicações nem lê segredos. Alterações em AMI/user data
são ignoradas no host existente, para evitar substituição automática; futuras
atualizações do host/guard exigem manutenção manual revisada. O serviço guard
é dependência do Docker e é reaplicado a cada boot. Sua implementação/testes
permanecem na #273; não há mudança de firewall na máquina do desenvolvedor.

## IAM e isolamento

`VintexStagingInstanceRole` permite autenticação ECR, pull dos dois repositórios
shared, acesso apenas à mídia/fila/parâmetros/logs staging e agente SSM.
Não permite push de imagens, leitura de backups/recursos prod nem consumo da DLQ.
A inspeção da DLQ é uma operação humana.

A policy `AmazonSSMManagedInstanceCore` contém GetParameter(s) com Resource `*`.
Por isso há **Deny explícito de `ssm:GetParameter*` fora de `/vintex/staging/*`**,
que prevalece sobre essa concessão. Recursos adicionais do Systems Manager que
precisem ler parâmetros fora desse caminho não fazem parte deste baseline.
API/worker usam a role pelo IMDS; proxy, db e FreeLLMAPI são bloqueados pelo
guard. Não colocar credenciais SSO nos contêineres ou na EC2.

`VintexStagingSchedulerRole` aceita somente o Scheduler da conta e do grupo
`vintex-staging`; Start/Stop se restringem ao ARN da instância e suas tags.
Os alvos universais EC2 têm janela flexível desativada, retry limitado a 2
vezes e idade máxima 300 s, para evitar ligar horas depois do horário.
Agendamento de desligamento após ativação sob demanda pertence ao pipeline futuro.

## Conta vazia: sequência manual

1. Seguir o [bootstrap da #272](./aws-shared.md#preparação-manual-de-uma-conta-vazia):
   IAM Identity Center/MFA, sessão SSO e bucket administrativo de state privado,
   versionado e criptografado em Ohio. Não é necessário ter nenhum bucket da
   aplicação previamente criado.
2. Revisar/aplicar `envs/shared`. Confirmar Budget, rede e dois repositórios ECR.
3. Conceder ao responsável acesso também à chave `vintex/staging/terraform.tfstate`
   e ao seu `.tflock` no bucket administrativo. A role da EC2 não acessa state.
4. Preparar staging na raiz do backend:

   ```bash
   cp infra/terraform/envs/staging/backend.tfbackend.example infra/terraform/envs/staging/backend.tfbackend
   cp infra/terraform/envs/staging/terraform.tfvars.example infra/terraform/envs/staging/terraform.tfvars
   aws sso login --profile vintex
   export AWS_PROFILE=vintex
   aws sts get-caller-identity
   terraform -chdir=infra/terraform/envs/shared output
   ```

   Informar o bucket e a conta real em `backend.tfbackend`; em `terraform.tfvars`,
   preencher `expected_account_id`, `shared_vpc_id` e `shared_public_subnet_id`
   com os outputs shared. Os exemplos são fictícios. Ambos os arquivos reais
   são ignorados pelo Git e pelo contexto de build Docker. O plano recusa
   VPC/subnet de outra conta, projeto/ambiente ou subnet sem IPv4 automático.

5. Inicializar o backend real e revisar o plano salvo antes de aplicar:

   ```bash
   terraform -chdir=infra/terraform/envs/staging init -input=false -backend-config=backend.tfbackend
   terraform -chdir=infra/terraform/envs/staging plan -out=staging.tfplan
   terraform -chdir=infra/terraform/envs/staging show staging.tfplan
   terraform -chdir=infra/terraform/envs/staging apply staging.tfplan
   terraform -chdir=infra/terraform/envs/staging output
   ```

   Confirmar conta, região, ausência de ingress e recursos exclusivos de staging.
   O primeiro apply pode criar somente os recursos desta issue; ele não faz deploy.
   **State/plan podem conter valores SecureString após refresh**, mesmo com
   `ignore_changes`. Proteger bucket, arquivos e acesso humano; não anexar
   state/plan reais à issue nem imprimir seus conteúdos em logs públicos.

6. Aguardar a instância ficar `Online` no Systems Manager. Abrir sessão:

   ```bash
   aws ssm start-session --profile vintex --region us-east-2 --target <INSTANCE_ID>
   ```

   Na EC2, verificar bootstrap sem imprimir env/segredos:

   ```bash
   sudo cloud-init status --wait
   sudo test -f /var/lib/vintex-staging/bootstrap-ready
   sudo systemctl is-active vintex-imds-guard.service docker amazon-ssm-agent
   sudo docker compose version
   /opt/vintex/deploy-venv/bin/python --version
   ```

   Se falhar, diagnosticar cloud-init antes de implantar; não desativar o guard
   para contornar falha. Boot real, downloads e capacidade ARM64 dependem da conta
   e ainda precisam de evidência operacional.

## Parâmetros e primeiro deploy

No console Parameter Store, substituir os valores de `db_password`, `jwt_secret`,
`llm_encryption_key`, `llm_admin_email` e `llm_admin_password`, conforme o
[contrato da #273](./aws-staging-runtime.md#parâmetros-e-ia). Todos são SecureString.
Terraform ignora futuras mudanças de valor; não gravar valores reais em tfvars.
Não trocar a chave de criptografia se o SQLite do FreeLLMAPI já contiver dados.

`llm_api_key` pode continuar provisório até configurar o dashboard. O script
ignora `REPLACE_MANUALLY_BEFORE_DEPLOY`: parâmetro obrigatório provisório impede
o deploy; token de IA provisório equivale a ausente. Sem token, o worker segue
a falha/retry/DLQ existente, e API/health continuam disponíveis. Gravar o token
unificado **apenas na AWS** depois de cadastrar provedores exclusivos de staging
e reexecutar o deploy para atualizar worker. A variável local `.env` permanece
inalterada. Chat/embeddings usam o provider indisponível já definido no runtime.
Cotas de produto ainda não implementadas não são entregues por esta issue.

Usar `runtime_resources` para preencher o config.json administrativo da #273.
Acrescentar SHA completo, paths do release e frontend; `parameter_path` é
informativo, o script já fixa `/vintex/staging/`. Fazer build/push ARM64,
espelhar FreeLLMAPI e transferir o build estático do front conforme o
[roteiro do runtime](./aws-staging-runtime.md#build-e-envio-manual-máquina-do-responsável).
O bootstrap já instala o guard e o venv do deploy; não é preciso exportar
credenciais na EC2. Executar o script da #273 como root com a role da instância.

Acesso ao front/API: túnel SSM porta 80 → localhost:8080. Dashboard: outro túnel
porta 3001 → localhost:3001. Não existe URL pública da staging; o túnel é
criptografado/autenticado. O front aprovado usa `VITE_API_BASE_URL=/api`.

## Horário e validação operacional

O apply lança a EC2 ligada, mesmo fora da janela. Após preparar/testar, desligar
manualmente se estiver fora do horário. Para testar sob demanda, o responsável
pode usar Start/Stop no console; os schedules recorrentes continuam ativos e
podem desligar a instância durante uma sessão. O pipeline futuro acrescentará
o desligamento após duas horas; por enquanto acompanhar o uso manualmente.
Stop preserva EBS e volumes, embora dados staging sejam exclusivamente sintéticos.
Não restaurar backups de produção neste ambiente.

Após o primeiro deploy, anexar evidências sem segredos:

- SSM Online, bootstrap/serviços saudáveis e front/health pelo túnel.
- IAM Policy Simulator: staging lê seus parâmetros e não parâmetros prod;
  acessa sua mídia/fila/logs/ECR pull e não backups, mídia/fila prod, push ECR
  ou administração IAM. Scheduler só controla esta instância.
- IMDS alcançável somente em API/worker; testar sem imprimir tokens/credenciais.
- Upload/leitura de mídia sintética, processamento ou falha/retry/DLQ de job,
  logs dos cinco serviços e persistência de dados após restart.
- Conferir os três schedules/timezone, parada/retomada, Budget e uso real do disco.
  A memória/disk e o custo devem ser medidos na conta; os testes mockados não
  comprovam comportamento operacional nem faturamento.

Não usar `terraform destroy` para rollback de release. Destruir staging remove
seu disco; esvaziar mídia sintética é uma operação manual explícita se necessária
antes de remover bucket. Shared tem state próprio e não é destruído junto.

## Verificações sem AWS

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/envs/staging init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/envs/staging validate
terraform -chdir=infra/terraform/envs/staging test
pytest tests/test_infra_staging_config.py tests/test_staging_runtime.py -v
```

Usar checkout separado se o diretório já foi inicializado com backend real.
Todos os testes Terraform usam provider mockado e plan: host, IAM, serviços,
Scheduler, outputs e recusa de inputs/rede incorretos. Pytest cobre contratos de
backend/provider, lifecycle, sintaxe/ordem do bootstrap e parâmetros provisórios.
CI valida `local`, `shared` e `staging`, sem credenciais ou apply. Downloads do
registry são necessários no init; isso não é acesso à conta AWS.

## Referências

- [SSM managed policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedInstanceCore.html)
- [Confiança do Scheduler por grupo e conta](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html)
- [Python no Amazon Linux 2023](https://docs.aws.amazon.com/linux/al2023/ug/python.html)
- [Docker Compose v5.6.0](https://github.com/docker/compose/releases/tag/v5.6.0)
