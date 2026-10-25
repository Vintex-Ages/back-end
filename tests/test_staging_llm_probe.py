"""Test the opt-in probe's acceptance and cleanup without starting containers."""

import json

import pytest

from scripts.infra import test_staging_llm as probe


@pytest.mark.parametrize("peak_mib,passed", [(372, True), (450, False)])
def test_probe_reports_headroom_and_cleans_synthetic_resources(
    monkeypatch, peak_mib, passed
):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args[0] == "info":
            return "x86_64"
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "State": {
                            "Running": True,
                            "Health": {"Status": "healthy"},
                            "OOMKilled": False,
                            "ExitCode": 0,
                        },
                        "NetworkSettings": {
                            "Networks": {args[1]: {"IPAddress": "172.20.0.2"}}
                        },
                    }
                ]
            )
        if args[0] == "exec":
            return str(peak_mib * probe.MIB)
        return ""

    def request(base, path, body=None, token=""):
        if path.endswith("login"):
            return 200, {"token": "synthetic-session"}
        if path.endswith("api-key"):
            return 200, {"apiKey": "synthetic-key"}
        if path.endswith("ping"):
            return 200, {}
        return (413 if "padding" in body else 503), {}

    monkeypatch.setattr(probe, "docker", docker)
    monkeypatch.setattr(probe, "request", request)
    report = probe.probe(512)
    assert report["passed"] is passed
    assert report["peak_mib"] == peak_mib
    assert report["payload_bytes"] > 32 * probe.MIB
    assert report["native_arm64"] is False
    assert any(call[:3] == ("network", "create", "--internal") for call in calls)
    assert any(call[:3] == ("rm", "-f", "-v") for call in calls)
    assert calls[-1][:2] == ("network", "rm")


def test_probe_cleans_resources_if_startup_fails(monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args[0] == "run":
            raise RuntimeError("Docker run failed")
        return ""

    monkeypatch.setattr(probe, "docker", docker)
    report = probe.probe(256)
    assert report["passed"] is False
    assert report["error"] == "RuntimeError"
    assert calls[-2][0] == "rm"
    assert calls[-1][:2] == ("network", "rm")
