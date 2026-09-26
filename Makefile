.PHONY: help infra-qa infra-up infra-down infra-local-test infra-complete \
        lint format-check \
        terraform-init terraform-fmt terraform-validate terraform-test \
        test-unit test-localstack test-ministack test-interoperability

# Infraestrutura de teste local (VE-12/VE-13/VE-20/VE-21/VE-22).
# Ver Vintex_Handoff_Infra_Local_Terraform_LocalStack_MiniStack.md para o
# contrato completo destes alvos.

COMPOSE_FILE := infra/vintex-infra/docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) --project-directory infra/vintex-infra
TF_DIR := infra/terraform/envs/local
TF := terraform -chdir=$(TF_DIR)

## --- Contrato principal ---------------------------------------------------

## Executa lint, verificação de formatação e validação do Terraform local.
infra-qa: lint format-check terraform-fmt terraform-init terraform-validate
	@echo "[infra-qa] ok"

## Sobe a infraestrutura local e cria recursos sintéticos de teste.
infra-up:
	$(COMPOSE) up -d --build --wait
	$(COMPOSE) exec -T api alembic upgrade head
	bash scripts/infra/seed-synthetic-resources.sh

## Derruba containers, redes e volumes da infraestrutura local.
infra-down:
	$(COMPOSE) down -v --remove-orphans

## Executa todos os testes locais sem derrubar a infraestrutura ao final.
infra-local-test: test-unit terraform-test test-localstack test-ministack test-interoperability
	@echo "[infra-local-test] ok"

# QA falhando aborta antes de subir containers. O script preserva a primeira
# falha e executa infra-down mesmo se QA, infra-up ou infra-local-test falhar.
## Executa QA, infraestrutura e testes; sempre derruba o ambiente no final.
infra-complete:
	@bash scripts/infra/complete.sh "$(MAKE)"

## --- Alvos granulares (diagnóstico) ----------------------------------------

## Executa a análise estática com Ruff.
lint:
	ruff check .

## Verifica a formatação do código com Black.
format-check:
	black --check .

## Inicializa o Terraform do ambiente local.
terraform-init:
	$(TF) init -input=false

## Verifica a formatação dos arquivos Terraform.
terraform-fmt:
	terraform fmt -check -recursive infra/terraform

# Nunca executa `terraform apply`.
## Valida a configuração Terraform sem aplicar mudanças.
terraform-validate: terraform-init
	$(TF) validate

## Executa os testes Terraform do ambiente local.
terraform-test:
	$(TF) test

## Executa os testes unitários do back-end no container da API.
test-unit:
	$(COMPOSE) exec -T api pytest tests/ -v

## Verifica recursos e operações reais no LocalStack (VE-20).
test-localstack:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.localstack_resources seed
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e VINTEX_INFRA_LOCALSTACK_TEST=1 api pytest tests/test_infra_localstack.py -v
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.localstack_resources verify

## Verifica recursos e operações reais no MiniStack (VE-21).
test-ministack:
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 api python -m scripts.infra.ministack_resources seed
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 -e VINTEX_INFRA_MINISTACK_TEST=1 api pytest tests/test_infra_ministack.py -v
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 api python -m scripts.infra.ministack_resources verify

## Verifica API, banco e fluxo sintético LocalStack/MiniStack (VE-22).
test-interoperability:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e MINISTACK_ENDPOINT_URL=http://ministack:4567 -e VINTEX_INFRA_INTEROP_TEST=1 api pytest tests/test_infra_interoperability.py -v

## --- Ajuda ----------------------------------------------------------------

## Mostra esta ajuda.
help:
	@printf "Uso: make <alvo>\\n"
	@awk '\
		/^## ---/ { printf "\n%s\n", substr($$0, 4); next } \
		/^## / { descricao = substr($$0, 4); next } \
		/^[a-zA-Z0-9][a-zA-Z0-9_-]*:/ && descricao != "" { \
			split($$0, alvo, ":"); \
			printf "  %-24s %s\n", alvo[1], descricao; \
			descricao = "" \
		}' $(MAKEFILE_LIST)
