"""Contrato de falha e teardown do `make infra-complete`."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/infra/complete.sh"


@pytest.mark.parametrize(
    ("failures", "expected_code", "expected_stages"),
    [
        ({}, 0, ["infra-qa", "infra-up", "infra-local-test", "infra-down"]),
        ({"infra-qa": 31}, 31, ["infra-qa", "infra-down"]),
        ({"infra-up": 32}, 32, ["infra-qa", "infra-up", "infra-down"]),
        (
            {"infra-local-test": 33},
            33,
            ["infra-qa", "infra-up", "infra-local-test", "infra-down"],
        ),
        (
            {"infra-local-test": 33, "infra-down": 34},
            33,
            ["infra-qa", "infra-up", "infra-local-test", "infra-down"],
        ),
        (
            {"infra-down": 34},
            34,
            ["infra-qa", "infra-up", "infra-local-test", "infra-down"],
        ),
    ],
)
def test_complete_preserves_first_failure_and_cleans_up(
    tmp_path: Path,
    failures: dict[str, int],
    expected_code: int,
    expected_stages: list[str],
) -> None:
    log = tmp_path / "stages.log"
    fake_make = tmp_path / "fake-make"
    fake_make.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$1" >> "$FAKE_MAKE_LOG"\n'
        'case "$1" in\n'
        '  infra-qa) exit "${FAIL_QA:-0}" ;;\n'
        '  infra-up) exit "${FAIL_UP:-0}" ;;\n'
        '  infra-local-test) exit "${FAIL_TEST:-0}" ;;\n'
        '  infra-down) exit "${FAIL_DOWN:-0}" ;;\n'
        "esac\n"
    )
    fake_make.chmod(0o755)
    env = {
        **os.environ,
        "FAKE_MAKE_LOG": str(log),
        "FAIL_QA": str(failures.get("infra-qa", 0)),
        "FAIL_UP": str(failures.get("infra-up", 0)),
        "FAIL_TEST": str(failures.get("infra-local-test", 0)),
        "FAIL_DOWN": str(failures.get("infra-down", 0)),
    }

    result = subprocess.run(
        ["bash", str(SCRIPT), str(fake_make)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_code, result.stderr
    assert log.read_text().splitlines() == expected_stages
