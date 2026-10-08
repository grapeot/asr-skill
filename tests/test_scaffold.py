import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import asr_skill
from asr_skill.cli import main
from asr_skill.contracts import (
    ASR_MODEL_ID,
    DIARIZATION_MODEL_ID,
    EXIT_NOT_IMPLEMENTED,
    EXIT_OK,
    EXIT_USAGE,
    PLANNED_COMMANDS,
)

ROOT = Path(__file__).resolve().parents[1]


def test_package_reports_scaffold():
    assert asr_skill.__version__ == "0.0.0"
    assert asr_skill.PHASE == "scaffold"
    assert asr_skill.IMPLEMENTED is False
    assert DIARIZATION_MODEL_ID == "nvidia/Nemotron-3-Diarization"
    assert ASR_MODEL_ID == "Qwen/Qwen3-ASR-1.7B"


def test_version_matches_pyproject():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == asr_skill.__version__


def test_version_command(capsys):
    assert main(["version"]) == EXIT_OK
    captured = capsys.readouterr()
    assert "phase=scaffold" in captured.out
    assert "implemented=false" in captured.out


def test_doctor_does_not_claim_models(capsys):
    assert main(["doctor"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["implemented"] is False
    assert payload["models_ready"] is False
    assert payload["network"] is False


def test_planned_commands_are_not_implemented(capsys):
    for name in PLANNED_COMMANDS:
        assert main([name, "--input", "/path/to/recordings"]) == EXIT_NOT_IMPLEMENTED
        payload = json.loads(capsys.readouterr().out)
        assert payload["error"] == "not_implemented"
        assert payload["command"] == name
        assert payload["implemented"] is False


def test_bare_call_is_usage(capsys):
    assert main([]) == EXIT_USAGE
    captured = capsys.readouterr()
    text = " ".join(captured.out.split())
    assert "does not transcribe" in text


def test_help_states_scaffold():
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_module_entrypoint():
    proc = subprocess.run(
        [sys.executable, "-m", "asr_skill", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "implemented=false" in proc.stdout


def test_launcher_script():
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "asr-skill"), "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "phase=scaffold" in proc.stdout
