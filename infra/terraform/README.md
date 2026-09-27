# Terraform (VE-13/VE-14/VE-16)

```
infra/terraform/
├── modules/
│   ├── network/       # VPC, subnets, rota de saída e security groups (VE-14)
│   ├── ecs_execution_role/ # papel mínimo de execução ECS (VE-14)
│   └── media_storage/ # bucket privado e prefixos de mídia (VE-16)
└── envs/
    └── local/        # único env desta sprint — provider AWS -> LocalStack/MiniStack
        ├── versions.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        └── tests/
            ├── local.tftest.hcl
            ├── network.tftest.hcl
            └── media_storage.tftest.hcl
```

Nenhum alvo do `Makefile` da raiz executa `terraform apply`. `make infra-qa` roda `fmt -check`, `init` e `validate`; `make infra-local-test` roda `terraform test` (mockado, via `mock_provider`, sem tocar LocalStack/MiniStack nem AWS real).

Envs de staging/prod contra AWS real ficam para quando a VE-27 (preparação para AWS real) sair do hold.

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
