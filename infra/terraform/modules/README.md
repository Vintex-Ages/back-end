# Módulos Terraform locais e AWS real

Módulos da base AWS compartilhada (#272), integrados ao root completo `aws` com `config/staging.tfvars`:

- `shared_network`: VPC EC2, uma subnet pública com IP automático, IGW e rota.
  O grupo da staging, sem ingress, pertence à #274. Não usa ECS/VPC Link.
- `container_registry`: ECRs privados `vintex-backend` e `freellmapi`, tags
  imutáveis, scan no push, AES256 e retenção de dez imagens por repositório.
- `project_budget`: Budget mensal de US$35 para toda a conta dedicada,
  alertas reais em 28/30/35 e previsão em 30, e-mails fornecidos localmente.

Os módulos herdam o provider AWS do ambiente. a composição staging restringe região/conta
e usa um state S3 completo, com lock nativo. Seus testes são planos mockados;
o apply real é manual. Veja [AWS compartilhada](../../../documentation/docs/infraestrutura/aws-shared.md).

Módulos da VE-14, VE-16 e VE-17:

- `network`: VPC com DNS habilitado, duas subnets em zonas diferentes, Internet
  Gateway e rota de saída. As subnets não atribuem IP público automaticamente.
  Security groups separados para API, worker e VPC Link não têm ingress público.
  Só o VPC Link alcança a porta 8000 da API; API e worker têm egress HTTPS.
- `ecs_execution_role`: confiança limitada a `ecs-tasks.amazonaws.com` e apenas
  a política gerenciada `AmazonECSTaskExecutionRolePolicy`, para ECR/logs.
  Permissões de aplicação para S3, SQS, banco e secrets ficam para as tasks
  específicas das issues posteriores.
- `media_storage` (VE-16): bucket S3 privado, bloqueio de ACLs/políticas
  públicas e criptografia AES256. Expõe o nome do bucket e os prefixos lógicos
  de fotos, vídeos curtos e comprovantes Pix. Os prefixos são proposta para
  alinhamento com a [VE-04 (#59)](https://github.com/Vintex-Ages/back-end/issues/59).
- `ai_messaging` (VE-17): fila SQS standard para análise de imagens e DLQ,
  com redrive após três entregas não confirmadas. Expõe nomes, URLs, ARNs e o
  limite de recebimentos para a configuração local.

ECS Fargate usa `awsvpc`: cada task ganha sua própria interface de rede (ENI)
na subnet escolhida. Não criamos `aws_network_interface` manualmente. A VE-19
deve consumir os IDs de subnet/security group expostos pelo módulo e decidir
explicitamente `assignPublicIp` para as tasks que precisam de saída HTTPS,
inclusive para obter imagens ECR e enviar logs. A rota via Internet Gateway
não fornece Internet a uma task sem IP público; sem NAT, a alternativa futura
é configurar endpoints VPC apropriados. Os security groups continuam sem
ingress público mesmo quando uma task recebe IP público. A VE-15 acrescentará
as regras necessárias para comunicação com PostgreSQL; até lá, o grupo da API
permite somente HTTPS de saída e entrada privada do VPC Link.

Os recursos declarados aqui são verificados apenas com `terraform test`
mockado. O ambiente local envia EC2 ao MiniStack e IAM ao LocalStack; ele não
executa `apply`. A base AWS real, backend remoto e Budget estão em `aws` com `config/staging.tfvars`
(#272), com provider separado.

PostgreSQL e pgvector (VE-15, #166/#185) são provisionados pelo Compose e pelas
migrations Alembic; não são módulos Terraform.

Módulos ainda em hold:

- Computação e descoberta (ECS/Fargate, Cloud Map, API Gateway, ECR, VPC Link) — VE-19

Worker e contrato de IA (VE-18, #169) foram incorporados pela PR #282. A staging
EC2 segue #272 → #273 → #274; a computação local ECS permanece em hold.

`envs/local` já expõe o provider AWS configurado para LocalStack/MiniStack; os módulos devem herdá-lo, sem reconfigurar o provider dentro de cada módulo.

## Staging EC2 real (#274)

- `staging_services`: reutiliza mídia e mensageria; bucket privado com TLS,
  fila/DLQ criptografadas (polling 20 s, visibilidade 180 s, DLQ 14 dias),
  parâmetros SecureString provisórios e cinco grupos de logs com retenção 7 dias.
- `staging_host`: AL2023 ARM64/t4g.small, EBS gp3 10 GB, nenhum ingress,
  IMDSv2, role mínima isolada e bootstrap do runtime #273, sem deploy.
- `staging_schedule`: start 10h/stop 22h seg–sex e sweep 02h diário, Brasília,
  role limitada ao ARN/tags da instância e trust da conta/grupo Scheduler.

Os tempos opcionais de `ai_messaging` preservam defaults locais e expõem o
contrato efetivo em `delivery_settings`. Staging usa `aws` com `config/staging.tfvars` no mesmo state de rede/ECR/Budget; [procedimento manual](../../../documentation/docs/infraestrutura/aws-staging.md).
