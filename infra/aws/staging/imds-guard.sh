#!/usr/bin/env bash
set -euo pipefail
# raw/PREROUTING sees container source IPs before NAT, even before Docker starts.
# Only API and worker may reach IMDSv2, on their fixed bridge/address pairs.
# Docker's default gateway may use either worker interface on Amazon Linux.
iptables -w -t raw -N VINTEX_IMDS 2>/dev/null || true
iptables-restore -w --noflush <<'RULES'
*raw
-F VINTEX_IMDS
-A VINTEX_IMDS -i br-vintex-app -s 172.30.73.3 -j RETURN
-A VINTEX_IMDS -i br-vintex-app -s 172.30.73.4 -j RETURN
-A VINTEX_IMDS -i br-vintex-llm -s 172.30.74.2 -j RETURN
-A VINTEX_IMDS -j DROP
COMMIT
RULES
for bridge in br-vintex-app br-vintex-llm; do
    iptables -w -t raw -C PREROUTING -i "$bridge" -d 169.254.169.254 -j VINTEX_IMDS 2>/dev/null ||
        iptables -w -t raw -I PREROUTING -i "$bridge" -d 169.254.169.254 -j VINTEX_IMDS
    # IPv6 is disabled on Compose networks; still block the IPv6 metadata endpoint.
    ip6tables -w -t raw -C PREROUTING -i "$bridge" -d fd00:ec2::254 -j DROP 2>/dev/null ||
        ip6tables -w -t raw -I PREROUTING -i "$bridge" -d fd00:ec2::254 -j DROP
done
