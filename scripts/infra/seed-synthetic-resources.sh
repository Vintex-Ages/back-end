#!/usr/bin/env bash
# Provisiona recursos sintéticos em LocalStack/MiniStack após `make infra-up`.
#
# A VE-20 provisiona LocalStack aqui. A VE-21 acrescenta MiniStack ao mesmo
# hook para que `make infra-up` prepare ambos sem duplicar a orquestração.

set -euo pipefail

docker compose \
  -f infra/vintex-infra/docker-compose.yml \
  --project-directory infra/vintex-infra \
  exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 \
  api python -m scripts.infra.localstack_resources seed
