# Terraform (VE-13/VE-14)

```
infra/terraform/
├── modules/
│   ├── network/       # VPC, subnets, rota de saída e security groups (VE-14)
│   └── ecs_execution_role/ # papel mínimo de execução ECS (VE-14)
└── envs/
    └── local/        # único env desta sprint — provider AWS -> LocalStack/MiniStack
        ├── versions.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        └── tests/
            ├── local.tftest.hcl
            └── network.tftest.hcl
```

Nenhum alvo do `Makefile` da raiz executa `terraform apply`. `make infra-qa` roda `fmt -check`, `init` e `validate`; `make infra-local-test` roda `terraform test` (mockado, via `mock_provider`, sem tocar LocalStack/MiniStack nem AWS real).

Envs de staging/prod contra AWS real ficam para quando a VE-27 (preparação para AWS real) sair do hold.

O ambiente `local` liga o provider EC2 ao MiniStack e IAM ao LocalStack. O
módulo de rede é descrito em [modules/README.md](modules/README.md). O plano
mockado verifica a composição e os contratos de saída sem criar VPC, role ou
outros recursos nos emuladores; os scripts de smoke test continuam usando
recursos sintéticos separados. Não executar `terraform apply` nesta fase.
