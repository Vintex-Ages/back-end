# Módulos Terraform

Módulos da VE-14 e VE-16:

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
executa `apply`. Um ambiente AWS real, backend remoto e orçamento dependem da
VE-27.

Módulos ainda em hold:

- Banco e busca vetorial (pgvector) — VE-15
- Mensageria assíncrona (SQS) — VE-17
- Worker e contrato de IA — VE-18
- Computação e descoberta (ECS/Fargate, Cloud Map, API Gateway, ECR, VPC Link) — VE-19

`envs/local` já expõe o provider AWS configurado para LocalStack/MiniStack; os módulos devem herdá-lo, sem reconfigurar o provider dentro de cada módulo.
