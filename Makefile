.PHONY: infra-qa infra-up infra-down infra-local-test infra-complete \
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

infra-qa: lint format-check terraform-fmt terraform-init terraform-validate
	@echo "[infra-qa] ok"

infra-up:
	$(COMPOSE) up -d --wait
	bash scripts/infra/seed-synthetic-resources.sh

infra-down:
	$(COMPOSE) down -v --remove-orphans

infra-local-test: test-unit terraform-test test-localstack test-ministack test-interoperability
	@echo "[infra-local-test] ok"

# Roda QA, sobe o ambiente, executa os testes e sempre derruba o ambiente no
# final (inclusive em falha), preservando o código de saída da primeira
# falha. infra-qa falhando aborta antes de subir qualquer container.
infra-complete:
	@set -e; \
	$(MAKE) infra-qa; \
	trap '$(MAKE) infra-down' EXIT; \
	$(MAKE) infra-up; \
	$(MAKE) infra-local-test

## --- Alvos granulares (diagnóstico) ----------------------------------------

lint:
	ruff check .

format-check:
	black --check .

terraform-init:
	$(TF) init -input=false

terraform-fmt:
	terraform fmt -check -recursive infra/terraform

# Nunca executa `terraform apply`.
terraform-validate: terraform-init
	$(TF) validate

terraform-test:
	$(TF) test

test-unit:
	pytest tests/ -v

# Implementados junto com as respectivas issues; por ora só sinalizam que
# ainda não fazem nada, sem quebrar infra-local-test/infra-complete.
test-localstack:
	@echo "[test-localstack] ainda não implementado — ver VE-20 (#171)"

test-ministack:
	@echo "[test-ministack] ainda não implementado — ver VE-21 (#172)"

test-interoperability:
	@echo "[test-interoperability] ainda não implementado — ver VE-22 (#173)"
