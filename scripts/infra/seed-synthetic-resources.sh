#!/usr/bin/env bash
# Provisiona recursos sintéticos em LocalStack/MiniStack após `make infra-up`.
#
# Intencionalmente um no-op nesta sprint: a VE-12 só entrega o Makefile e o
# Compose vintex-infra. Provisionar S3/SQS/Secrets/IAM/STS sintéticos é
# escopo da VE-20 (LocalStack) e ECS/Cloud Map/API Gateway/ECR sintéticos é
# escopo da VE-21 (MiniStack) — este script é o ponto de extensão que elas
# vão preencher, para não duplicar o hook em outro lugar do Makefile.

set -euo pipefail

echo "[seed-synthetic-resources] nada a provisionar ainda (aguardando VE-20/VE-21)."
