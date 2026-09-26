#!/usr/bin/env bash
# Provisiona recursos sintéticos em LocalStack/MiniStack após `make infra-up`.
#
# VE-20 e VE-21 preparam ambos os emuladores pelo mesmo hook.

set -euo pipefail

docker compose \
  -f infra/vintex-infra/docker-compose.yml \
  --project-directory infra/vintex-infra \
  exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 \
  api python -m scripts.infra.localstack_resources seed

docker compose \
  -f infra/vintex-infra/docker-compose.yml \
  --project-directory infra/vintex-infra \
  exec -T -e LOCALSTACK_ENDPOINT_URL=http://localstack:4566 \
  api python -m scripts.infra.media_storage_resources seed

docker compose \
  -f infra/vintex-infra/docker-compose.yml \
  --project-directory infra/vintex-infra \
  exec -T -e MINISTACK_ENDPOINT_URL=http://ministack:4567 \
  api python -m scripts.infra.ministack_resources seed
