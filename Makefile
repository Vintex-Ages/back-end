.PHONY: help infra-qa infra-up infra-down infra-local-test infra-complete \
        infra-api-image lint format-check \
        terraform-init terraform-fmt terraform-validate terraform-test \
        terraform-plan terraform-show terraform-apply terraform-output infra-deploy \
        test-unit test-infra-postgres test-localstack test-sqs test-media-storage test-ministack test-interoperability test-ai-worker

# Infraestrutura de teste local (VE-12/VE-13/VE-16/VE-17/VE-20/VE-21/VE-22).
# Ver Vintex_Handoff_Infra_Local_Terraform_LocalStack_MiniStack.md para o
# contrato completo destes alvos.

COMPOSE_FILE := infra/vintex-infra/docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) --project-directory infra/vintex-infra
API_IMAGE := vintex-infra-api:local
QA_RUN := docker run --rm --network none \
	--mount "type=bind,source=$(CURDIR),target=/app,readonly" \
	--workdir /app $(API_IMAGE)
# GNU Make treats the environment token as another goal: accept only an
# explicit, finite set and reject typos before running any Terraform command.
TF_ACTIONS := terraform-init terraform-validate terraform-test terraform-plan terraform-show terraform-apply terraform-output infra-deploy
TF_GOALS := $(filter $(TF_ACTIONS),$(MAKECMDGOALS))
TF_ENV_GOALS := $(filter local bootstrap staging,$(MAKECMDGOALS))
TF_SELECTED_ENV := $(if $(TF_ENV_GOALS),$(TF_ENV_GOALS),local)
ifneq ($(strip $(TF_ENV_GOALS)),)
ifeq ($(strip $(TF_GOALS)),)
$(error Use make terraform-validate staging ou make infra-deploy staging; alvos infra-* locais não recebem ambiente)
endif
endif
ifneq ($(strip $(TF_GOALS)),)
ifneq ($(words $(TF_GOALS)),1)
$(error Execute um comando Terraform por vez: make terraform-validate staging)
endif
ifneq ($(words $(TF_ENV_GOALS)),0)
ifneq ($(words $(TF_ENV_GOALS)),1)
$(error Informe um único ambiente: make terraform-validate staging ou make terraform-validate local)
endif
endif
ifneq ($(strip $(filter-out $(TF_ACTIONS) local bootstrap staging,$(MAKECMDGOALS))),)
$(error Comando/ambiente inválido. Use make terraform-validate staging ou make infra-deploy staging)
endif
endif
TF_DIR := infra/terraform/envs/local
AWS_TF := python3 scripts/infra/terraform_env.py
TF := terraform -chdir=$(TF_DIR)

.PHONY: local bootstrap staging
local bootstrap staging:
ifeq ($(strip $(TF_GOALS)),)
	@echo "Informe o comando: make terraform-validate $@ ou make infra-deploy staging" >&2
	@exit 2
else
	@:
endif

## --- Contrato principal ---------------------------------------------------

## Executa lint, verificação de formatação e validação do Terraform local.
infra-qa: lint format-check terraform-fmt terraform-validate
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
infra-local-test: test-unit terraform-test test-infra-postgres test-localstack test-sqs test-media-storage test-ministack test-interoperability test-ai-worker
	@echo "[infra-local-test] ok"

# QA falhando aborta antes de subir containers. O script preserva a primeira
# falha e executa infra-down mesmo se QA, infra-up ou infra-local-test falhar.
## Executa QA, infraestrutura e testes; sempre derruba o ambiente no final.
infra-complete:
	@bash scripts/infra/complete.sh "$(MAKE)"

## --- Alvos granulares (diagnóstico) ----------------------------------------

## Constrói a imagem que fornece as ferramentas Python fixadas do projeto.
infra-api-image:
	$(COMPOSE) build api

## Executa a análise estática com Ruff na imagem da API.
lint: infra-api-image
	$(QA_RUN) ruff check --no-cache .

## Verifica a formatação com Black na imagem da API.
format-check: infra-api-image
	$(QA_RUN) black --check .

## Inicializa o backend selecionado: make terraform-init staging (não cria recursos).
terraform-init:
ifeq ($(TF_SELECTED_ENV),local)
	$(TF) init -input=false
else
	$(AWS_TF) init --env $(TF_SELECTED_ENV)
endif

## Verifica a formatação dos arquivos Terraform.
terraform-fmt:
	terraform fmt -check -recursive infra/terraform

## Valida sem conta AWS: make terraform-validate staging (default: local).
terraform-validate:
	$(AWS_TF) validate --env $(TF_SELECTED_ENV)

## Executa planos mockados sem conta AWS: make terraform-test staging.
terraform-test:
	$(AWS_TF) test --env $(TF_SELECTED_ENV)

## Salva um plano AWS: make terraform-plan staging.
terraform-plan:
	$(AWS_TF) plan --env $(TF_SELECTED_ENV)

## Exibe o plano AWS salvo: make terraform-show staging.
terraform-show:
	$(AWS_TF) show --env $(TF_SELECTED_ENV)

## Aplica somente o plano salvo, após confirmação: make terraform-apply staging.
terraform-apply:
	$(AWS_TF) apply --env $(TF_SELECTED_ENV)

## Exibe outputs da infraestrutura: make terraform-output staging.
terraform-output:
	$(AWS_TF) output --env $(TF_SELECTED_ENV)

## Conduz bucket e staging completa com planos e confirmação: make infra-deploy staging.
infra-deploy:
	$(AWS_TF) deploy --env $(TF_SELECTED_ENV)

## Executa os testes unitários do back-end no container da API.
test-unit:
	$(COMPOSE) exec -T api pytest tests/ -v

## Verifica PostgreSQL, migrations e persistência no Compose vintex-infra (VE-15).
test-infra-postgres:
	$(COMPOSE) exec -T -e VINTEX_INFRA_POSTGRES_TEST=1 api pytest tests/test_infra_postgres.py -v
	$(COMPOSE) exec -T api sh -c 'TEST_POSTGRES_URL="$$DATABASE_URL" TEST_POSTGRES_REUSE_MIGRATED_DB=1 pytest tests/ -v -m postgres'

## Verifica recursos e operações reais no LocalStack (VE-20).
test-localstack:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.localstack_resources seed
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e VINTEX_INFRA_LOCALSTACK_TEST=1 api pytest tests/test_infra_localstack.py -v
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.localstack_resources verify

## Verifica contrato, retries e DLQ de análise de imagens no LocalStack.
test-sqs:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.sqs_resources seed
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e VINTEX_INFRA_SQS_TEST=1 api pytest tests/test_infra_sqs.py -v
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.sqs_resources verify

## Verifica bucket privado e operações de mídia reais no LocalStack (VE-16).
test-media-storage:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.media_storage_resources seed
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e VINTEX_INFRA_MEDIA_TEST=1 api pytest tests/test_infra_media_storage.py -v
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 api python -m scripts.infra.media_storage_resources verify

## Verifica recursos e operações reais no MiniStack (VE-21).
test-ministack:
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 api python -m scripts.infra.ministack_resources seed
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 -e VINTEX_INFRA_MINISTACK_TEST=1 api pytest tests/test_infra_ministack.py -v
	$(COMPOSE) exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 api python -m scripts.infra.ministack_resources verify

## Verifica API, banco e fluxo sintético LocalStack/MiniStack (VE-22).
test-interoperability:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e MINISTACK_ENDPOINT_URL=http://ministack:4567 -e VINTEX_INFRA_INTEROP_TEST=1 api pytest tests/test_infra_interoperability.py -v

## Verifica API, mídia, worker, persistência e DLQ no Docker local.
test-ai-worker:
	$(COMPOSE) exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 -e VINTEX_INFRA_AI_WORKER_TEST=1 api pytest tests/test_infra_ai_worker.py tests/test_infra_ai_worker_e2e.py -v

## --- Ajuda ----------------------------------------------------------------

## Mostra esta ajuda.
help:
	@printf "Uso: make <alvo> [local|bootstrap|staging]\\n"
	@awk '\
		/^## ---/ { printf "\n%s\n", substr($$0, 4); next } \
		/^## / { descricao = substr($$0, 4); next } \
		/^[a-zA-Z0-9][a-zA-Z0-9_-]*:/ && descricao != "" { \
			split($$0, alvo, ":"); \
			printf "  %-24s %s\n", alvo[1], descricao; \
			descricao = "" \
		}' $(MAKEFILE_LIST)
