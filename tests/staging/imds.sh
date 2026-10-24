#!/usr/bin/env bash
set -euo pipefail
# This entire test runs in a disposable privileged container with --network none.
# Metadata is a synthetic local HTTP server; no EC2 or host firewall is used.
ip link add br-vintex-app type bridge
ip address add 172.30.73.1/24 dev br-vintex-app
ip link set br-vintex-app up
ip address add 169.254.169.254/32 dev lo
python -m http.server 80 --bind 169.254.169.254 >/dev/null 2>&1 &
server_pid=$!
trap 'kill "$server_pid"' EXIT
for suffix in 2 3 4 5; do
    ip netns add "service$suffix"
    ip link add "host$suffix" type veth peer name "guest$suffix"
    ip link set "host$suffix" master br-vintex-app
    ip link set "host$suffix" up
    ip link set "guest$suffix" netns "service$suffix"
    ip -n "service$suffix" address add "172.30.73.$suffix/24" dev "guest$suffix"
    ip -n "service$suffix" link set "guest$suffix" up
    ip -n "service$suffix" link set lo up
    ip -n "service$suffix" route add default via 172.30.73.1
done
ip link add br-vintex-llm type bridge
ip address add 172.30.74.1/24 dev br-vintex-llm
ip link set br-vintex-llm up
ip netns add llm
ip link add hostllm type veth peer name guestllm
ip link set hostllm master br-vintex-llm
ip link set hostllm up
ip link set guestllm netns llm
ip -n llm address add 172.30.74.3/24 dev guestllm
ip -n llm link set guestllm up
ip -n llm link set lo up
ip -n llm route add default via 172.30.74.1
# The real worker has two fixed interfaces. Both valid bridge/address pairs
# must work, independently of the gateway selected by Docker 25.
ip link add hostworkerllm type veth peer name guestworkerllm
ip link set hostworkerllm master br-vintex-llm
ip link set hostworkerllm up
ip link set guestworkerllm netns service4
ip -n service4 address add 172.30.74.2/24 dev guestworkerllm
ip -n service4 link set guestworkerllm up
ip -n service4 route get 169.254.169.254 | grep -q 'src 172.30.73.4'
sleep 1
bash /guard.sh
bash /guard.sh # Reapply must remain idempotent.
for allowed in service3 service4; do
    ip netns exec "$allowed" curl -sf --max-time 2 http://169.254.169.254/ >/dev/null
done
for denied in service2 service5 llm; do
    if ip netns exec "$denied" curl -sf --max-time 1 http://169.254.169.254/ >/dev/null; then
        echo "IMDS unexpectedly reachable: $denied" >&2
        exit 1
    fi
done
# The worker retains its instance-role access when Docker chooses llm.
ip -n service4 route replace default via 172.30.74.1
ip netns exec service4 curl -sf --max-time 2 http://169.254.169.254/ >/dev/null
# A valid worker source on the wrong bridge must still be rejected. Give
# replies an explicit route so a routing failure cannot mask a broken guard.
ip route add 172.30.73.4/32 via 172.30.74.2 dev br-vintex-llm
if ip netns exec service4 curl --interface 172.30.73.4 -sf --max-time 1 http://169.254.169.254/ >/dev/null; then
    echo 'IMDS unexpectedly reachable from app source on llm bridge' >&2
    exit 1
fi
ip route del 172.30.73.4/32
ip -n service4 route replace default via 172.30.73.1
ip netns exec service4 curl -sf --max-time 2 http://169.254.169.254/ >/dev/null
ip route add 172.30.74.2/32 via 172.30.73.4 dev br-vintex-app
if ip netns exec service4 curl --interface 172.30.74.2 -sf --max-time 1 http://169.254.169.254/ >/dev/null; then
    echo 'IMDS unexpectedly reachable from llm source on app bridge' >&2
    exit 1
fi
ip route del 172.30.74.2/32
echo '[staging-imds] API/worker allowed; proxy/db/FreeLLMAPI blocked'
