# Módulos Terraform

Vazio por enquanto. Cada módulo de feature entra aqui quando a issue correspondente sair do hold:

- Rede e segurança (VPC, subnets, security groups) — VE-14
- Banco e busca vetorial (pgvector) — VE-15
- Storage de mídia (S3) — VE-16
- Mensageria assíncrona (SQS) — VE-17
- Worker e contrato de IA — VE-18
- Computação e descoberta (ECS/Fargate, Cloud Map, API Gateway, ECR, VPC Link) — VE-19

`envs/local` já expõe o provider AWS configurado para LocalStack/MiniStack; os módulos acima devem importá-lo, não reconfigurar o provider.
