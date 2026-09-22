# Terraform (VE-13)

```
infra/terraform/
├── modules/          # módulos de feature (vazio nesta sprint, ver modules/README.md)
└── envs/
    └── local/        # único env desta sprint — provider AWS -> LocalStack/MiniStack
        ├── versions.tf
        ├── variables.tf
        ├── main.tf
        ├── outputs.tf
        └── tests/
            └── local.tftest.hcl
```

Nenhum alvo do `Makefile` da raiz executa `terraform apply`. `make infra-qa` roda `fmt -check`, `init` e `validate`; `make infra-local-test` roda `terraform test` (mockado, via `mock_provider`, sem tocar LocalStack/MiniStack nem AWS real).

Envs de staging/prod contra AWS real ficam para quando a VE-27 (preparação para AWS real) sair do hold.
