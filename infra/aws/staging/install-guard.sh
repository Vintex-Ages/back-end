#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
runtime_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -m 0755 "$runtime_dir/imds-guard.sh" /usr/local/sbin/vintex-imds-guard
install -m 0644 "$runtime_dir/vintex-imds-guard.service" /etc/systemd/system/vintex-imds-guard.service
install -d -m 0755 /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/vintex-imds.conf <<'UNIT'
[Unit]
Requires=vintex-imds-guard.service
After=vintex-imds-guard.service
UNIT
systemctl daemon-reload
systemctl enable vintex-imds-guard.service
systemctl restart vintex-imds-guard.service
